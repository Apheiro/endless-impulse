use serde::Serialize;
use std::collections::{BTreeMap, HashMap, HashSet, VecDeque};
use std::ffi::{CStr, CString, OsStr};
use std::fs;
use std::io;
use std::os::fd::{AsRawFd, FromRawFd, IntoRawFd, OwnedFd};
use std::os::unix::ffi::OsStrExt;
use std::path::{Component, Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU64, AtomicUsize, Ordering};
use std::sync::{Arc, Condvar, Mutex};
use std::thread;
use std::time::{Duration, Instant};

pub const DEFAULT_MAX_DEPTH: usize = 128;
const ERROR_SAMPLES: usize = 16;

#[derive(Default)]
pub struct Progress {
    pub directories: AtomicU64,
    pub files: AtomicU64,
    pub bytes: AtomicU64,
}
#[derive(Serialize)]
pub struct Counters {
    pub directories_seen: u64,
    pub files_seen: u64,
    pub allocated_bytes_processed: u64,
}
impl Progress {
    pub fn get(&self) -> Counters {
        Counters {
            directories_seen: self.directories.load(Ordering::Relaxed),
            files_seen: self.files.load(Ordering::Relaxed),
            allocated_bytes_processed: self.bytes.load(Ordering::Relaxed),
        }
    }
}
#[derive(Clone, Debug, Serialize)]
pub struct Issue {
    pub code: String,
    pub category: &'static str,
    pub errno: Option<i32>,
    // Relative child name, never a global event path. Bounded samples per node.
    pub name_hex: Option<String>,
}
#[derive(Debug)]
pub struct Node {
    pub name: Vec<u8>,
    pub parent: Option<usize>,
    pub children: Vec<usize>,
    pub own_bytes: u64,
    pub direct_bytes: u64,
    pub direct_entries: u64,
    pub excluded_entries: u64,
    pub total_bytes: u64,
    pub issue_count: u64,
    pub subtree_issues: u64,
    pub issues: Vec<Issue>,
    pub unreadable_count: u64,
    pub unstable_entries: u64,
    pub uncertain_count: u64,
    pub subtree_unreadable: u64,
    pub subtree_unstable: u64,
    pub subtree_uncertain: u64,
    // Only diagnosed nodes allocate a map; keep healthy nodes to one pointer,
    // rather than embedding a map header in every retained directory.
    #[allow(clippy::box_collection)]
    issue_codes: Option<Box<BTreeMap<&'static str, u64>>>,
    pub exclusion: Option<&'static str>,
}
impl Node {
    fn new(name: Vec<u8>, parent: Option<usize>, own_bytes: u64) -> Self {
        Self {
            name,
            parent,
            children: vec![],
            own_bytes,
            direct_bytes: 0,
            direct_entries: 0,
            excluded_entries: 0,
            total_bytes: 0,
            issue_count: 0,
            subtree_issues: 0,
            issues: vec![],
            unreadable_count: 0,
            unstable_entries: 0,
            uncertain_count: 0,
            subtree_unreadable: 0,
            subtree_unstable: 0,
            subtree_uncertain: 0,
            issue_codes: None,
            exclusion: None,
        }
    }
    fn issue(&mut self, code: &'static str, errno: Option<i32>, name: Option<&[u8]>) {
        self.issue_count += 1;
        *self
            .issue_codes
            .get_or_insert_with(Default::default)
            .entry(code)
            .or_default() += 1;
        let category = match code {
            "directory_changed" | "directory_metadata_changed" => {
                self.unstable_entries += 1;
                self.uncertain_count += u64::from(code == "directory_changed");
                "unstable"
            }
            _ => {
                self.unreadable_count += 1;
                "unreadable"
            }
        };
        if self.issues.len() < ERROR_SAMPLES {
            self.issues.push(Issue {
                code: code.into(),
                category,
                errno,
                name_hex: name.map(hex),
            });
        }
    }
}
pub struct Snapshot {
    pub root: PathBuf,
    pub nodes: Vec<Node>,
    pub elapsed_ms: u64,
    pub root_dev: u64,
    pub root_ino: u64,
    pub mount_id: u64,
    pub summary: Summary,
    pub execution: Execution,
}
impl Snapshot {
    pub fn path_bytes(&self, mut node: usize) -> Vec<u8> {
        let mut pieces = vec![];
        while let Some(parent) = self.nodes[node].parent {
            pieces.push(self.nodes[node].name.as_slice());
            node = parent;
        }
        pieces.reverse();
        pieces.join(&b'/')
    }
    pub fn lookup(&self, path: &[u8]) -> Option<usize> {
        if path.starts_with(b"/") {
            return None;
        }
        let mut node = 0;
        for part in path
            .split(|b| *b == b'/')
            .filter(|p| !p.is_empty() && *p != b".")
        {
            if part == b".." {
                return None;
            }
            node = *self.nodes[node]
                .children
                .iter()
                .find(|&&id| self.nodes[id].name == part)?;
        }
        Some(node)
    }
}

#[derive(Default, Debug, Serialize)]
pub struct Summary {
    pub unstable_entries: u64,
    pub unreadable_count: u64,
    pub excluded_count: u64,
    pub uncertain_directories: u64,
    pub issue_codes: BTreeMap<&'static str, u64>,
}
#[derive(Default, Debug, Serialize)]
pub struct Execution {
    pub workers_limit: usize,
    pub workers_used: usize,
    pub queue_peak: usize,
    pub hardlinks_retained: usize,
}
#[derive(Clone, Copy, PartialEq, Eq)]
pub enum ScanPhase {
    DirectoryOpened,
    BeforeDirectoryFinish,
    BeforeFold,
}
pub type VisitHook = Arc<dyn Fn(&Path, ScanPhase) + Send + Sync>;

#[derive(Default, Clone)]
pub struct Options {
    pub max_depth: Option<usize>,
    /// 1..=4; None defaults to 2. No disk-type guess is made.
    pub workers: Option<usize>,
    /// Library-only deterministic fixture observation, never exposed via IPC.
    pub visit_hook: Option<VisitHook>,
    /// Tests can inject mount boundaries and errors without mounting/chmod/sudo.
    pub boundaries: Option<HashSet<PathBuf>>,
    pub faults: HashMap<PathBuf, i32>,
    pub entry_faults: HashMap<PathBuf, i32>,
    pub read_faults: HashMap<PathBuf, i32>,
    pub mount_faults: HashMap<PathBuf, i32>,
}
#[derive(Debug)]
pub enum ScanError {
    Cancelled,
    Failed(&'static str, Option<i32>),
}

pub fn hex(bytes: &[u8]) -> String {
    const DIGITS: &[u8] = b"0123456789abcdef";
    let mut s = String::with_capacity(bytes.len() * 2);
    for &b in bytes {
        s.push(DIGITS[(b >> 4) as usize] as char);
        s.push(DIGITS[(b & 15) as usize] as char);
    }
    s
}
pub fn unhex(s: &str) -> Option<Vec<u8>> {
    if s.len() % 2 != 0 {
        return None;
    }
    s.as_bytes()
        .chunks_exact(2)
        .map(|p| {
            let hi = (p[0] as char).to_digit(16)?;
            let lo = (p[1] as char).to_digit(16)?;
            Some((hi * 16 + lo) as u8)
        })
        .collect()
}
fn normalize(path: &Path) -> Result<PathBuf, ScanError> {
    if !path.is_absolute() {
        return Err(ScanError::Failed("absolute_root_required", None));
    }
    let mut result = PathBuf::from("/");
    for part in path.components() {
        match part {
            Component::Normal(p) => result.push(p),
            Component::RootDir | Component::CurDir => (),
            _ => return Err(ScanError::Failed("parent_component_forbidden", None)),
        }
    }
    Ok(result)
}
fn open_at(fd: i32, name: &CStr) -> io::Result<OwnedFd> {
    // SAFETY: C string is terminated; successful descriptor becomes uniquely owned.
    let raw = unsafe {
        libc::openat(
            fd,
            name.as_ptr(),
            libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
        )
    };
    if raw < 0 {
        Err(io::Error::last_os_error())
    } else {
        Ok(unsafe { OwnedFd::from_raw_fd(raw) })
    }
}
fn open_root(path: &Path) -> io::Result<OwnedFd> {
    let mut fd = open_at(libc::AT_FDCWD, c"/")?;
    for part in path.components() {
        if let Component::Normal(name) = part {
            let name = CString::new(name.as_bytes())?;
            fd = open_at(fd.as_raw_fd(), &name)?;
        }
    }
    Ok(fd)
}
fn stat_at(fd: i32, name: &CStr) -> io::Result<libc::stat> {
    let mut st = std::mem::MaybeUninit::uninit();
    // SAFETY: valid output storage and directory fd; do not follow final symlink.
    if unsafe {
        libc::fstatat(
            fd,
            name.as_ptr(),
            st.as_mut_ptr(),
            libc::AT_SYMLINK_NOFOLLOW,
        )
    } != 0
    {
        Err(io::Error::last_os_error())
    } else {
        Ok(unsafe { st.assume_init() })
    }
}
struct Identity {
    mount: u64,
    dev: u64,
    ino: u64,
}
fn identity(fd: i32) -> io::Result<Identity> {
    let mut st = std::mem::MaybeUninit::<libc::statx>::zeroed();
    // SAFETY: valid descriptor, empty terminated name and output storage.
    let rc = unsafe {
        libc::statx(
            fd,
            c"".as_ptr(),
            libc::AT_EMPTY_PATH | libc::AT_SYMLINK_NOFOLLOW,
            libc::STATX_MNT_ID | libc::STATX_INO,
            st.as_mut_ptr(),
        )
    };
    if rc != 0 {
        return Err(io::Error::last_os_error());
    }
    let st = unsafe { st.assume_init() };
    if st.stx_mask & (libc::STATX_MNT_ID | libc::STATX_INO) != libc::STATX_MNT_ID | libc::STATX_INO
    {
        return Err(io::Error::from_raw_os_error(libc::ENOTSUP));
    }
    Ok(Identity {
        mount: st.stx_mnt_id,
        dev: libc::makedev(st.stx_dev_major, st.stx_dev_minor),
        ino: st.stx_ino,
    })
}
fn stat_fd(fd: i32) -> io::Result<libc::stat> {
    let mut st = std::mem::MaybeUninit::uninit();
    // SAFETY: valid descriptor and output storage.
    if unsafe { libc::fstat(fd, st.as_mut_ptr()) } != 0 {
        Err(io::Error::last_os_error())
    } else {
        Ok(unsafe { st.assume_init() })
    }
}

struct Dir {
    raw: *mut libc::DIR,
}
impl Dir {
    fn open(fd: OwnedFd) -> io::Result<Self> {
        // fdopendir takes ownership only on success. No dup/fcntl is needed.
        let fd = fd.into_raw_fd();
        let raw = unsafe { libc::fdopendir(fd) };
        if raw.is_null() {
            let e = io::Error::last_os_error();
            unsafe {
                libc::close(fd);
            }
            Err(e)
        } else {
            Ok(Self { raw })
        }
    }
    fn fd(&self) -> i32 {
        unsafe { libc::dirfd(self.raw) }
    }
    fn next(&mut self) -> io::Result<Option<CString>> {
        loop {
            // SAFETY: this thread exclusively owns DIR. Copy d_name before next call.
            unsafe {
                *libc::__errno_location() = 0;
                let entry = libc::readdir(self.raw);
                if entry.is_null() {
                    let errno = *libc::__errno_location();
                    return if errno == 0 {
                        Ok(None)
                    } else {
                        Err(io::Error::from_raw_os_error(errno))
                    };
                }
                let name = CStr::from_ptr((*entry).d_name.as_ptr()).to_bytes();
                if name != b"." && name != b".." {
                    return Ok(Some(
                        CString::new(name).expect("readdir names contain no NUL"),
                    ));
                }
            }
        }
    }
}
impl Drop for Dir {
    fn drop(&mut self) {
        unsafe {
            libc::closedir(self.raw);
        }
    }
}
struct Task {
    id: usize,
    node: Node,
    fd: OwnedFd,
    path: PathBuf,
    depth: usize,
    initial: libc::stat,
}
struct Frame {
    task: TaskData,
    dir: Dir,
}
struct TaskData {
    id: usize,
    node: Node,
    path: PathBuf,
    depth: usize,
    initial: libc::stat,
}
fn directory_change(before: &libc::stat, after: &libc::stat) -> Option<&'static str> {
    if after.st_nlink == 0 {
        Some("directory_removed")
    } else if after.st_mtime != before.st_mtime || after.st_mtime_nsec != before.st_mtime_nsec {
        Some("directory_changed")
    } else if after.st_ctime != before.st_ctime || after.st_ctime_nsec != before.st_ctime_nsec {
        Some("directory_metadata_changed")
    } else {
        None
    }
}
fn unescape_mount(s: &[u8]) -> Vec<u8> {
    let mut out = vec![];
    let mut i = 0;
    while i < s.len() {
        if s[i] == b'\\'
            && i + 3 < s.len()
            && s[i + 1..i + 4].iter().all(|b| (b'0'..=b'7').contains(b))
        {
            out.push((s[i + 1] - b'0') * 64 + (s[i + 2] - b'0') * 8 + s[i + 3] - b'0');
            i += 4;
        } else {
            out.push(s[i]);
            i += 1;
        }
    }
    out
}
pub fn mount_boundaries(data: &[u8]) -> HashSet<PathBuf> {
    data.split(|b| *b == b'\n')
        .filter_map(|line| {
            let field = line.split(|b| *b == b' ').nth(4)?;
            Some(PathBuf::from(OsStr::from_bytes(&unescape_mount(field))))
        })
        .collect()
}
fn allocated(st: &libc::stat) -> u64 {
    (st.st_blocks.max(0) as u64).saturating_mul(512)
}

// Only outstanding directory tasks and DFS frames hold descriptors. Ordinary
// files never enter a task queue or retained list.
struct Scheduler {
    queue: VecDeque<Task>,
    outstanding: usize,
    peak: usize,
}
struct LinkOwner {
    node: usize,
    path: Vec<u8>,
    bytes: u64,
}
struct Context<'a> {
    root: &'a Path,
    options: &'a Options,
    cancel: &'a AtomicBool,
    progress: &'a Progress,
    root_dev: u64,
    root_mount: u64,
    boundaries: HashMap<PathBuf, HashSet<Vec<u8>>>,
    nodes: Mutex<Vec<Node>>,
    links: Mutex<HashMap<(u64, u64), LinkOwner>>,
    scheduler: Mutex<Scheduler>,
    ready: Condvar,
    helpers: AtomicUsize,
    workers: usize,
    failed: AtomicBool,
}
struct BufferedProgress<'a> {
    progress: &'a Progress,
    files: u64,
    bytes: u64,
}
impl BufferedProgress<'_> {
    fn flush(&mut self) {
        self.progress.files.fetch_add(self.files, Ordering::Relaxed);
        self.progress.bytes.fetch_add(self.bytes, Ordering::Relaxed);
        self.files = 0;
        self.bytes = 0;
    }
}
impl Drop for BufferedProgress<'_> {
    fn drop(&mut self) {
        self.flush();
    }
}
impl Context<'_> {
    fn stopped(&self) -> bool {
        self.cancel.load(Ordering::Relaxed) || self.failed.load(Ordering::Relaxed)
    }
    fn hook(&self, path: &Path, phase: ScanPhase) {
        if let Some(hook) = &self.options.visit_hook {
            hook(path, phase);
        }
    }
    fn store(&self, id: usize, node: Node) {
        self.nodes.lock().unwrap()[id] = node;
    }
    fn reserve(&self) -> usize {
        let mut nodes = self.nodes.lock().unwrap();
        let id = nodes.len();
        nodes.push(Node::new(vec![], None, 0));
        self.progress.directories.fetch_add(1, Ordering::Relaxed);
        id
    }
    fn is_boundary(&self, parent: &Path, name: &[u8]) -> bool {
        self.boundaries
            .get(parent)
            .is_some_and(|names| names.contains(name))
    }
    fn enter(&self, task: Task) -> Option<Frame> {
        let Task {
            id,
            mut node,
            fd,
            path,
            depth,
            initial,
        } = task;
        if let Some(errno) = self.options.read_faults.get(&path) {
            node.issue("read_directory", Some(*errno), None);
            self.store(id, node);
            return None;
        }
        match Dir::open(fd) {
            Ok(dir) => {
                self.hook(&path, ScanPhase::DirectoryOpened);
                Some(Frame {
                    task: TaskData {
                        id,
                        node,
                        path,
                        depth,
                        initial,
                    },
                    dir,
                })
            }
            Err(e) => {
                node.issue("read_directory", e.raw_os_error(), None);
                self.store(id, node);
                None
            }
        }
    }
    fn finish(&self, mut frame: Frame) {
        self.hook(&frame.task.path, ScanPhase::BeforeDirectoryFinish);
        match stat_fd(frame.dir.fd()) {
            Ok(st) => {
                if let Some(code) = directory_change(&frame.task.initial, &st) {
                    frame.task.node.issue(code, None, None);
                }
            }
            Err(e) => frame
                .task
                .node
                .issue("directory_stat", e.raw_os_error(), None),
        }
        self.store(frame.task.id, frame.task.node);
    }
    fn account_link(&self, parent: usize, path: Vec<u8>, st: &libc::stat) {
        let mut links = self.links.lock().unwrap();
        let key = (st.st_dev, st.st_ino);
        match links.entry(key) {
            std::collections::hash_map::Entry::Vacant(e) => {
                e.insert(LinkOwner {
                    node: parent,
                    path,
                    bytes: allocated(st),
                });
                self.progress
                    .bytes
                    .fetch_add(allocated(st), Ordering::Relaxed);
            }
            std::collections::hash_map::Entry::Occupied(mut e) => {
                if path < e.get().path {
                    self.progress
                        .bytes
                        .fetch_sub(e.get().bytes, Ordering::Relaxed);
                    self.progress
                        .bytes
                        .fetch_add(allocated(st), Ordering::Relaxed);
                    e.insert(LinkOwner {
                        node: parent,
                        path,
                        bytes: allocated(st),
                    });
                }
            }
        }
    }
    // A tiny tree stays on the caller without even creating helper threads.
    // Queue capacity is 2*workers; when full the owning worker descends locally.
    fn submit<'scope, 'env>(
        &'scope self,
        scope: &'scope thread::Scope<'scope, 'env>,
        task: Task,
    ) -> Option<Task> {
        if self.workers == 1
            || (self.progress.directories.load(Ordering::Relaxed) < 16
                && self.progress.files.load(Ordering::Relaxed) < 256)
        {
            return Some(task);
        }
        let mut scheduler = self.scheduler.lock().unwrap();
        if scheduler.queue.len() >= self.workers * 2 {
            return Some(task);
        }
        scheduler.queue.push_back(task);
        scheduler.outstanding += 1;
        scheduler.peak = scheduler.peak.max(scheduler.queue.len());
        self.ready.notify_one();
        drop(scheduler);
        if self
            .helpers
            .fetch_update(Ordering::Relaxed, Ordering::Relaxed, |h| {
                (h < self.workers - 1).then_some(h + 1)
            })
            .is_ok()
            && thread::Builder::new()
                .name("storage-scan".into())
                .spawn_scoped(scope, || self.guarded(scope))
                .is_err()
        {
            self.failed.store(true, Ordering::Relaxed);
            self.ready.notify_all();
        }
        None
    }
    fn guarded<'scope, 'env>(&'scope self, scope: &'scope thread::Scope<'scope, 'env>) {
        if std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| self.worker(scope))).is_err() {
            self.failed.store(true, Ordering::Relaxed);
            self.ready.notify_all();
        }
    }
    fn worker<'scope, 'env>(&'scope self, scope: &'scope thread::Scope<'scope, 'env>) {
        loop {
            let task = {
                let mut scheduler = self.scheduler.lock().unwrap();
                loop {
                    if self.stopped() {
                        return;
                    }
                    if let Some(task) = scheduler.queue.pop_front() {
                        break task;
                    }
                    if scheduler.outstanding == 0 {
                        return;
                    }
                    scheduler = self
                        .ready
                        .wait_timeout(scheduler, Duration::from_millis(25))
                        .unwrap()
                        .0;
                }
            };
            self.walk(scope, task);
            let mut scheduler = self.scheduler.lock().unwrap();
            scheduler.outstanding -= 1;
            if scheduler.outstanding == 0 {
                self.ready.notify_all();
            }
        }
    }
    fn walk<'scope, 'env>(&'scope self, scope: &'scope thread::Scope<'scope, 'env>, task: Task) {
        let mut stack = vec![];
        if let Some(frame) = self.enter(task) {
            stack.push(frame);
        }
        let mut buffered = BufferedProgress {
            progress: self.progress,
            files: 0,
            bytes: 0,
        };
        while !stack.is_empty() {
            if self.stopped() {
                return;
            }
            let frame = stack.last_mut().unwrap();
            let name = match frame.dir.next() {
                Ok(Some(name)) => name,
                Ok(None) => {
                    self.finish(stack.pop().unwrap());
                    buffered.flush();
                    continue;
                }
                Err(e) => {
                    frame
                        .task
                        .node
                        .issue("read_directory", e.raw_os_error(), None);
                    self.finish(stack.pop().unwrap());
                    buffered.flush();
                    continue;
                }
            };
            // The fixture branch allocates no path in ordinary production scans.
            if !self.options.entry_faults.is_empty() {
                let path = frame.task.path.join(OsStr::from_bytes(name.as_bytes()));
                if let Some(errno) = self.options.entry_faults.get(&path) {
                    frame
                        .task
                        .node
                        .issue("stat_entry", Some(*errno), Some(name.as_bytes()));
                    continue;
                }
            }
            let st = match stat_at(frame.dir.fd(), &name) {
                Ok(st) => st,
                Err(e) => {
                    frame
                        .task
                        .node
                        .issue("stat_entry", e.raw_os_error(), Some(name.as_bytes()));
                    continue;
                }
            };
            if st.st_mode & libc::S_IFMT != libc::S_IFDIR {
                if st.st_dev != self.root_dev || self.is_boundary(&frame.task.path, name.as_bytes())
                {
                    frame.task.node.excluded_entries += 1;
                    continue;
                }
                buffered.files += 1;
                frame.task.node.direct_entries += 1;
                if st.st_mode & libc::S_IFMT == libc::S_IFREG && st.st_nlink > 1 {
                    let path = frame.task.path.join(OsStr::from_bytes(name.as_bytes()));
                    self.account_link(
                        frame.task.id,
                        path.strip_prefix(self.root)
                            .expect("anchored descendant")
                            .as_os_str()
                            .as_bytes()
                            .to_vec(),
                        &st,
                    );
                } else {
                    frame.task.node.direct_bytes += allocated(&st);
                    buffered.bytes += allocated(&st);
                }
                if buffered.files >= 256 {
                    buffered.flush();
                }
                continue;
            }
            let id = self.reserve();
            let parent = frame.task.id;
            frame.task.node.children.push(id);
            let path = frame.task.path.join(OsStr::from_bytes(name.as_bytes()));
            let mut node = Node::new(name.as_bytes().to_vec(), Some(parent), 0);
            if st.st_dev != self.root_dev
                || self.is_boundary(&frame.task.path, name.as_bytes())
                || (self.root == Path::new("/")
                    && [b"proc".as_slice(), b"sys", b"dev"].contains(&name.as_bytes())
                    && parent == 0)
            {
                node.exclusion = Some("mount_boundary");
                self.store(id, node);
                continue;
            }
            if self.root == Path::new("/") && parent == 0 && name.as_bytes() == b"root" {
                node.exclusion = Some("protected_path");
                self.store(id, node);
                continue;
            }
            node.own_bytes = allocated(&st);
            self.progress
                .bytes
                .fetch_add(node.own_bytes, Ordering::Relaxed);
            let depth = frame.task.depth + 1;
            if depth > self.options.max_depth.unwrap_or(DEFAULT_MAX_DEPTH) {
                node.issue("depth_limit", None, None);
                self.store(id, node);
                continue;
            }
            if let Some(errno) = self.options.faults.get(&path) {
                node.issue("open_directory", Some(*errno), None);
                self.store(id, node);
                continue;
            }
            let fd = match open_at(frame.dir.fd(), &name) {
                Ok(fd) => fd,
                Err(e) => {
                    node.issue("open_directory", e.raw_os_error(), None);
                    self.store(id, node);
                    continue;
                }
            };
            if let Some(errno) = self.options.mount_faults.get(&path) {
                node.issue("mount_identity_unavailable", Some(*errno), None);
                self.store(id, node);
                continue;
            }
            // One statx validates BOTH identity and mount ID (replaces fstatat + statx).
            match identity(fd.as_raw_fd()) {
                Ok(opened) if opened.mount != self.root_mount => {
                    self.progress
                        .bytes
                        .fetch_sub(node.own_bytes, Ordering::Relaxed);
                    node.own_bytes = 0;
                    node.exclusion = Some("mount_boundary");
                    self.store(id, node);
                    continue;
                }
                Ok(opened) if opened.dev == st.st_dev && opened.ino == st.st_ino => (),
                Ok(_) => {
                    node.issue("directory_replaced", None, None);
                    self.store(id, node);
                    continue;
                }
                Err(e) => {
                    node.issue("mount_identity_unavailable", e.raw_os_error(), None);
                    self.store(id, node);
                    continue;
                }
            }
            let task = Task {
                id,
                node,
                fd,
                path,
                depth,
                initial: st,
            };
            if let Some(task) = self.submit(scope, task) {
                if let Some(frame) = self.enter(task) {
                    stack.push(frame);
                }
            }
        }
    }
}

pub fn scan(
    root: &Path,
    options: &Options,
    cancel: &AtomicBool,
    progress: &Progress,
) -> Result<Snapshot, ScanError> {
    let started = Instant::now();
    let workers = options.workers.unwrap_or(2);
    if !(1..=4).contains(&workers) {
        return Err(ScanError::Failed("invalid_workers", None));
    }
    if cancel.load(Ordering::Relaxed) {
        return Err(ScanError::Cancelled);
    }
    let root = normalize(root)?;
    let fd =
        open_root(&root).map_err(|e| ScanError::Failed("root_open_failed", e.raw_os_error()))?;
    let root_st = stat_fd(fd.as_raw_fd())
        .map_err(|e| ScanError::Failed("root_stat_failed", e.raw_os_error()))?;
    let root_mount = identity(fd.as_raw_fd())
        .map_err(|e| ScanError::Failed("mount_identity_unavailable", e.raw_os_error()))?
        .mount;
    let mount_data = fs::read("/proc/self/mountinfo")
        .map_err(|e| ScanError::Failed("mountinfo_unavailable", e.raw_os_error()))?;
    let boundaries = options
        .boundaries
        .clone()
        .unwrap_or_else(|| mount_boundaries(&mount_data));
    let mut boundary_names: HashMap<PathBuf, HashSet<Vec<u8>>> = HashMap::new();
    for path in boundaries {
        if let (Some(parent), Some(name)) = (path.parent(), path.file_name()) {
            boundary_names
                .entry(parent.into())
                .or_default()
                .insert(name.as_bytes().to_vec());
        }
    }
    let root_anchor = open_at(fd.as_raw_fd(), c".")
        .map_err(|e| ScanError::Failed("root_open_failed", e.raw_os_error()))?;
    let root_bytes = allocated(&root_st);
    progress.directories.store(1, Ordering::Relaxed);
    progress.bytes.store(root_bytes, Ordering::Relaxed);
    progress.files.store(0, Ordering::Relaxed);
    let context = Context {
        root: &root,
        options,
        cancel,
        progress,
        root_dev: root_st.st_dev,
        root_mount,
        boundaries: boundary_names,
        nodes: Mutex::new(vec![Node::new(vec![], None, 0)]),
        links: Mutex::new(HashMap::new()),
        scheduler: Mutex::new(Scheduler {
            queue: VecDeque::from([Task {
                id: 0,
                node: Node::new(vec![], None, root_bytes),
                fd,
                path: root.clone(),
                depth: 0,
                initial: root_st,
            }]),
            outstanding: 1,
            peak: 1,
        }),
        ready: Condvar::new(),
        helpers: AtomicUsize::new(0),
        workers,
        failed: AtomicBool::new(false),
    };
    thread::scope(|scope| context.guarded(scope));
    if context.failed.load(Ordering::Relaxed) {
        return Err(ScanError::Failed("worker_failed", None));
    }
    if cancel.load(Ordering::Relaxed) {
        return Err(ScanError::Cancelled);
    }
    if fs::read("/proc/self/mountinfo").ok().as_ref() != Some(&mount_data) {
        return Err(ScanError::Failed("mounts_changed", None));
    }
    let reopened =
        open_root(&root).map_err(|e| ScanError::Failed("root_changed", e.raw_os_error()))?;
    let end_id = identity(reopened.as_raw_fd())
        .map_err(|e| ScanError::Failed("root_changed", e.raw_os_error()))?;
    if end_id.dev != root_st.st_dev
        || end_id.ino != root_st.st_ino
        || end_id.mount != root_mount
        || identity(root_anchor.as_raw_fd()).ok().map(|i| i.mount) != Some(root_mount)
    {
        return Err(ScanError::Failed("root_changed", None));
    }
    context.hook(&root, ScanPhase::BeforeFold);
    let execution = Execution {
        workers_limit: workers,
        workers_used: context.helpers.load(Ordering::Relaxed) + 1,
        queue_peak: context.scheduler.lock().unwrap().peak,
        hardlinks_retained: context.links.lock().unwrap().len(),
    };
    let mut nodes = context
        .nodes
        .into_inner()
        .map_err(|_| ScanError::Failed("worker_failed", None))?;
    // Attribute each hardlink exactly once AFTER all workers have resolved its owner.
    for (_, owner) in context
        .links
        .into_inner()
        .map_err(|_| ScanError::Failed("worker_failed", None))?
    {
        if cancel.load(Ordering::Relaxed) {
            return Err(ScanError::Cancelled);
        }
        nodes[owner.node].direct_bytes += owner.bytes;
    }
    let mut summary = Summary::default();
    for id in (0..nodes.len()).rev() {
        if cancel.load(Ordering::Relaxed) {
            return Err(ScanError::Cancelled);
        }
        summary.excluded_count +=
            nodes[id].excluded_entries + u64::from(nodes[id].exclusion.is_some());
        if let Some(codes) = &nodes[id].issue_codes {
            for (&code, &count) in codes.iter() {
                *summary.issue_codes.entry(code).or_default() += count;
            }
        }
        // Cache ranking in the existing child vector, without a second index tree.
        let mut children = std::mem::take(&mut nodes[id].children);
        children.sort_unstable_by(|a, b| {
            nodes[*b]
                .total_bytes
                .cmp(&nodes[*a].total_bytes)
                .then_with(|| nodes[*a].name.cmp(&nodes[*b].name))
        });
        nodes[id].children = children;
        nodes[id].total_bytes += nodes[id].own_bytes + nodes[id].direct_bytes;
        nodes[id].subtree_issues += nodes[id].issue_count;
        nodes[id].subtree_unreadable += nodes[id].unreadable_count;
        nodes[id].subtree_unstable += nodes[id].unstable_entries;
        nodes[id].subtree_uncertain += nodes[id].uncertain_count;
        if let Some(p) = nodes[id].parent {
            nodes[p].total_bytes += nodes[id].total_bytes;
            nodes[p].subtree_issues += nodes[id].subtree_issues;
            nodes[p].subtree_unreadable += nodes[id].subtree_unreadable;
            nodes[p].subtree_unstable += nodes[id].subtree_unstable;
            nodes[p].subtree_uncertain += nodes[id].subtree_uncertain;
        }
    }
    if cancel.load(Ordering::Relaxed) {
        return Err(ScanError::Cancelled);
    }
    summary.unreadable_count = nodes[0].subtree_unreadable;
    summary.unstable_entries = nodes[0].subtree_unstable;
    summary.uncertain_directories = nodes[0].subtree_uncertain;
    Ok(Snapshot {
        root,
        nodes,
        elapsed_ms: started.elapsed().as_millis() as u64,
        root_dev: root_st.st_dev,
        root_ino: root_st.st_ino,
        mount_id: root_mount,
        summary,
        execution,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn metadata_only_entry_change_and_unlink_are_distinct() {
        // Pure metadata fixture: no chmod or real filesystem access required.
        let original: libc::stat = unsafe { std::mem::zeroed() };
        let mut before = original;
        before.st_nlink = 2;
        let mut after = before;
        after.st_ctime_nsec += 1;
        assert_eq!(
            directory_change(&before, &after),
            Some("directory_metadata_changed")
        );
        let mut node = Node::new(vec![], None, 0);
        node.issue("directory_metadata_changed", None, None);
        assert_eq!(
            (
                node.unreadable_count,
                node.unstable_entries,
                node.uncertain_count
            ),
            (0, 1, 0)
        );
        after.st_mtime_nsec += 1;
        assert_eq!(directory_change(&before, &after), Some("directory_changed"));
        node.issue("directory_changed", None, None);
        assert_eq!(
            (
                node.unreadable_count,
                node.unstable_entries,
                node.uncertain_count
            ),
            (0, 2, 1)
        );
        after.st_nlink = 0;
        assert_eq!(directory_change(&before, &after), Some("directory_removed"));
        node.issue("directory_removed", None, None);
        assert_eq!(node.unreadable_count, 1);
    }
}
