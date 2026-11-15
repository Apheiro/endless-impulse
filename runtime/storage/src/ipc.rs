use crate::scan::{self, Options, Progress, ScanError, Snapshot};
use serde::Deserialize;
use serde_json::{Value, json};
use std::io::{self, BufRead, Write};
use std::os::unix::ffi::OsStringExt;
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, mpsc};
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

pub const MAX_INPUT: usize = 65_536;
pub const MAX_OUTPUT: usize = 262_144;
pub const MAX_PAGE: usize = 128;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Request {
    pub id: String,
    pub action: String,
    pub root: Option<String>,
    pub workers: Option<usize>,
    pub root_hex: Option<String>,
    pub scan_id: Option<String>,
    pub path: Option<String>,
    pub path_hex: Option<String>,
    pub node_id: Option<usize>,
    pub offset: Option<usize>,
    pub limit: Option<usize>,
    pub sort: Option<String>,
    pub chart_width: Option<u32>,
    pub query: Option<String>,
    pub others: Option<bool>,
    pub directories_only: Option<bool>,
}
pub fn parse(line: &[u8]) -> Result<Request, &'static str> {
    let req: Request = serde_json::from_slice(line).map_err(|_| "invalid_request")?;
    if req.id.is_empty() || req.id.len() > 128 {
        return Err("invalid_id");
    }
    Ok(req)
}
fn error(id: Value, code: &str) -> Value {
    json!({"protocol":1,"type":"response","id":id,"ok":false,"error":{"code":code}})
}
fn ok(id: &str, action: &str, data: Value) -> Value {
    json!({"protocol":1,"type":"response","id":id,"action":action,"ok":true,"data":data})
}
fn bytes_arg(text: &Option<String>, raw: &Option<String>) -> Result<Option<Vec<u8>>, &'static str> {
    match (text, raw) {
        (Some(_), Some(_)) => Err("ambiguous_path"),
        (_, Some(raw)) => scan::unhex(raw).map(Some).ok_or("invalid_hex"),
        (Some(text), _) => Ok(Some(text.as_bytes().to_vec())),
        _ => Ok(None),
    }
}
struct Job {
    scan_id: String,
    request_id: String,
    state: &'static str,
    started: Instant,
    elapsed_ms: Option<u64>,
    progress: Arc<Progress>,
    cancel: Arc<AtomicBool>,
    seq: u64,
}
struct Pending {
    root: PathBuf,
    workers: usize,
}
struct Done {
    scan_id: String,
    result: Result<Snapshot, ScanError>,
}

/// All protocol writes and published state live on the dispatcher thread.
/// Exactly one scan coordinator is permitted; its bounded pool is joined before
/// replacement starts. Replacement requests coalesce into one pending slot.
pub struct Engine {
    options: Options,
    session: String,
    generation: u64,
    current: Option<Job>,
    pending: Option<Pending>,
    running: Option<String>,
    worker_cancel: Option<Arc<AtomicBool>>,
    snapshot: Option<Snapshot>,
    tx: mpsc::SyncSender<Done>,
    rx: mpsc::Receiver<Done>,
    pub closed: bool,
}
impl Default for Engine {
    fn default() -> Self {
        Self::new()
    }
}
impl Engine {
    pub fn new() -> Self {
        let workers = std::env::var("ENDLESS_STORAGE_WORKERS")
            .ok()
            .and_then(|v| v.parse::<usize>().ok())
            .filter(|w| (1..=4).contains(w));
        Self::with_options(Options {
            workers,
            ..Options::default()
        })
    }
    /// Library-only fixture injection; never accepted over IPC.
    pub fn with_options(options: Options) -> Self {
        let (tx, rx) = mpsc::sync_channel(1);
        let epoch = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos();
        Self {
            options,
            session: format!("{}-{epoch}", std::process::id()),
            generation: 0,
            current: None,
            pending: None,
            running: None,
            worker_cancel: None,
            snapshot: None,
            tx,
            rx,
            closed: false,
        }
    }
    fn event(&mut self, event: &str, extra: Value) -> Value {
        let job = self.current.as_mut().unwrap();
        job.seq += 1;
        if matches!(
            job.state,
            "finished" | "finished-with-warnings" | "failed" | "aborted"
        ) && job.elapsed_ms.is_none()
        {
            job.elapsed_ms = Some(job.started.elapsed().as_millis() as u64);
        }
        json!({"protocol":1,"type":"event","event":event,"request_id":job.request_id,
            "scan_id":job.scan_id,"seq":job.seq,"state":job.state,"data":extra})
    }
    fn status(&self) -> Value {
        match &self.current {
            Some(job) => json!({"scan_id":job.scan_id,"request_id":job.request_id,
                "state":job.state,"elapsed_ms":job.elapsed_ms.unwrap_or_else(|| job.started.elapsed().as_millis() as u64),
                "progress":job.progress.get()}),
            None => json!({"state":"idle"}),
        }
    }
    fn start_pending(&mut self) {
        if self.running.is_some() {
            return;
        }
        let Some(pending) = self.pending.take() else {
            return;
        };
        let job = self.current.as_mut().unwrap();
        job.state = "scanning";
        let scan_id = job.scan_id.clone();
        self.running = Some(scan_id.clone());
        let cancel = job.cancel.clone();
        self.worker_cancel = Some(cancel.clone());
        let progress = job.progress.clone();
        let tx = self.tx.clone();
        let mut options = self.options.clone();
        options.workers = Some(pending.workers);
        thread::spawn(move || {
            let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                scan::scan(&pending.root, &options, &cancel, &progress)
            }))
            .unwrap_or(Err(ScanError::Failed("worker_failed", None)));
            let _ = tx.send(Done { scan_id, result });
        });
    }
    pub fn poll(&mut self) -> Vec<Value> {
        let mut output = vec![];
        if let Ok(done) = self.rx.try_recv() {
            self.running = None;
            self.worker_cancel = None;
            if self
                .current
                .as_ref()
                .is_some_and(|j| j.scan_id == done.scan_id && !matches!(j.state, "aborted"))
            {
                let result = if self
                    .current
                    .as_ref()
                    .unwrap()
                    .cancel
                    .load(Ordering::Relaxed)
                {
                    Err(ScanError::Cancelled)
                } else {
                    done.result
                };
                let extra = match result {
                    Ok(snapshot) => {
                        let warnings = snapshot.nodes[0].subtree_issues;
                        let unreadable = snapshot.summary.unreadable_count;
                        self.current.as_mut().unwrap().state = if unreadable == 0 {
                            "finished"
                        } else {
                            "finished-with-warnings"
                        };
                        let data = json!({"total_bytes":snapshot.nodes[0].total_bytes,
                            "issue_count":warnings,"directories_retained":snapshot.nodes.len(),
                            "elapsed_ms":snapshot.elapsed_ms,
                            "excluded_count":snapshot.summary.excluded_count,
                            "unstable_entries":snapshot.summary.unstable_entries,
                            "unreadable_count":unreadable,
                            "changes_observed":snapshot.summary.unstable_entries > 0,
                            "coverage_incomplete":unreadable > 0,
                            "coverage_uncertain":snapshot.summary.uncertain_directories > 0,
                            "uncertain_directories":snapshot.summary.uncertain_directories,
                            "issue_codes":snapshot.summary.issue_codes,"execution":snapshot.execution,
                            "identity":{"dev":snapshot.root_dev.to_string(),"ino":snapshot.root_ino.to_string(),"mount_id":snapshot.mount_id.to_string()}});
                        self.snapshot = Some(snapshot);
                        data
                    }
                    Err(ScanError::Cancelled) => {
                        self.current.as_mut().unwrap().state = "aborted";
                        json!({"reason":"cancelled"})
                    }
                    Err(ScanError::Failed(code, errno)) => {
                        self.current.as_mut().unwrap().state = "failed";
                        json!({"error":{"code":code,"errno":errno}})
                    }
                };
                output.push(self.event("completed", extra));
            }
            self.start_pending();
        }
        output
    }
    pub fn progress_event(&mut self) -> Option<Value> {
        if self
            .current
            .as_ref()
            .is_some_and(|j| matches!(j.state, "scanning" | "queued" | "cancelling"))
        {
            Some(self.event("progress", self.status()))
        } else {
            None
        }
    }
    pub fn handle_line(&mut self, line: &[u8]) -> Vec<Value> {
        match parse(line) {
            Ok(req) => match self.handle(&req) {
                Ok(output) => output,
                Err(code) => vec![error(json!(req.id), code)],
            },
            Err(code) => vec![error(Value::Null, code)],
        }
    }
    fn handle(&mut self, req: &Request) -> Result<Vec<Value>, &'static str> {
        let mut out = vec![];
        match req.action.as_str() {
            "scan" => {
                let workers = req.workers.or(self.options.workers).unwrap_or(2);
                if !(1..=4).contains(&workers) {
                    return Err("invalid_workers");
                }
                let root = bytes_arg(&req.root, &req.root_hex)?.ok_or("root_required")?;
                if root.contains(&0) || root.len() > 16_384 || !root.starts_with(b"/") {
                    return Err("invalid_root");
                }
                if root.split(|b| *b == b'/').any(|p| p == b"..") {
                    return Err("parent_component_forbidden");
                }
                if self
                    .current
                    .as_ref()
                    .is_some_and(|j| matches!(j.state, "queued" | "scanning" | "cancelling"))
                {
                    self.current
                        .as_mut()
                        .unwrap()
                        .cancel
                        .store(true, Ordering::Relaxed);
                    self.current.as_mut().unwrap().state = "aborted";
                    out.push(self.event("completed", json!({"reason":"superseded"})));
                }
                if let Some(cancel) = &self.worker_cancel {
                    cancel.store(true, Ordering::Relaxed);
                }
                self.generation += 1;
                self.snapshot = None;
                self.current = Some(Job {
                    scan_id: format!("{}-{}", self.session, self.generation),
                    request_id: req.id.clone(),
                    state: "queued",
                    started: Instant::now(),
                    elapsed_ms: None,
                    progress: Arc::new(Progress::default()),
                    cancel: Arc::new(AtomicBool::new(false)),
                    seq: 0,
                });
                self.pending = Some(Pending {
                    root: PathBuf::from(std::ffi::OsString::from_vec(root)),
                    workers,
                });
                self.start_pending();
                out.push(ok(&req.id, "scan", self.status()));
            }
            "status" | "progress" => {
                out.push(ok(&req.id, &req.action, self.status()));
            }
            "cancel" => {
                self.check_scan(req)?;
                let job = self.current.as_mut().unwrap();
                if matches!(job.state, "scanning" | "queued" | "cancelling") {
                    job.cancel.store(true, Ordering::Relaxed);
                    if self.pending.take().is_some() {
                        job.state = "aborted";
                        out.push(self.event("completed", json!({"reason":"cancelled"})));
                    } else {
                        job.state = "cancelling";
                    }
                }
                out.push(ok(&req.id, "cancel", self.status()));
            }
            "browse" => {
                self.check_scan(req)?;
                let snapshot = self.snapshot.as_ref().ok_or("snapshot_not_ready")?;
                out.push(ok(&req.id, "browse", browse(snapshot, req)?));
            }
            "close" | "shutdown" => {
                if let Some(cancel) = &self.worker_cancel {
                    cancel.store(true, Ordering::Relaxed);
                }
                self.pending = None;
                self.closed = true;
                out.push(ok(&req.id, &req.action, json!({"state":"closed"})));
            }
            _ => return Err("unknown_action"),
        }
        Ok(out)
    }
    fn check_scan(&self, req: &Request) -> Result<(), &'static str> {
        let job = self.current.as_ref().ok_or("no_scan")?;
        if req.scan_id.as_deref() != Some(job.scan_id.as_str()) {
            return Err("stale_scan");
        }
        Ok(())
    }
}
impl Drop for Engine {
    fn drop(&mut self) {
        if let Some(cancel) = &self.worker_cancel {
            cancel.store(true, Ordering::Relaxed);
        }
    }
}
fn node_json(s: &Snapshot, id: usize) -> Value {
    let n = &s.nodes[id];
    json!({"node_id":id,"name":String::from_utf8_lossy(&n.name),"name_hex":scan::hex(&n.name),
        "type":"directory","allocated_bytes":n.total_bytes,"own_bytes":n.own_bytes,
        "direct_files_bytes":n.direct_bytes,"direct_entries":n.direct_entries,"excluded_entries":n.excluded_entries,
        "child_directories":n.children.len(),"issue_count":n.issue_count,
        "subtree_issue_count":n.subtree_issues,
        "unreadable_count":n.unreadable_count,"unstable_entries":n.unstable_entries,
        "subtree_unreadable_count":n.subtree_unreadable,"subtree_unstable_entries":n.subtree_unstable,
        "coverage_incomplete":n.subtree_unreadable > 0,"coverage_uncertain":n.subtree_uncertain > 0,
        "changes_observed":n.subtree_unstable > 0,"complete":n.subtree_issues == 0 && n.exclusion.is_none(),"issues":n.issues,
        "issue_samples_truncated":n.issue_count > n.issues.len() as u64,"exclusion":n.exclusion})
}
pub fn browse(s: &Snapshot, req: &Request) -> Result<Value, &'static str> {
    if req.node_id.is_some() && (req.path.is_some() || req.path_hex.is_some()) {
        return Err("ambiguous_path");
    }
    let path = bytes_arg(&req.path, &req.path_hex)?;
    let id = match req.node_id {
        Some(id) if id < s.nodes.len() => id,
        Some(_) => return Err("node_not_found"),
        None => s
            .lookup(path.as_deref().unwrap_or(b""))
            .ok_or("node_not_found")?,
    };
    let limit = req.limit.unwrap_or(64);
    if limit == 0 || limit > MAX_PAGE {
        return Err("invalid_limit");
    }
    let sort = req.sort.as_deref().unwrap_or("size_desc");
    if !["size_desc", "size_asc", "name"].contains(&sort) {
        return Err("invalid_sort");
    }
    let n = &s.nodes[id];
    // One index per child directory, never per file. Files are one synthetic row.
    let mut children: Vec<Option<usize>> = n.children.iter().copied().map(Some).collect();
    if n.direct_entries > 0 {
        children.push(None);
    }
    let size = |key: &Option<usize>| {
        key.map(|k| s.nodes[k].total_bytes)
            .unwrap_or(n.direct_bytes)
    };
    let name = |key: &Option<usize>| key.map(|k| s.nodes[k].name.as_slice()).unwrap_or(b"");
    if sort != "size_desc" {
        children.sort_unstable_by(|a, b| {
            let order = match sort {
                "size_desc" => size(b).cmp(&size(a)),
                "size_asc" => size(a).cmp(&size(b)),
                _ => std::cmp::Ordering::Equal,
            };
            order.then_with(|| name(a).cmp(name(b)))
        });
    } else if n.direct_entries > 0 {
        // The cached directory order needs only insertion of the synthetic row.
        children.pop();
        let at = children.partition_point(|key| size(key) > n.direct_bytes);
        children.insert(at, None);
    }
    // Chart membership uses ALL child directories, independently of pagination,
    // search, list ordering and the synthetic direct-files row.
    // Children are ranked once during finalization of this immutable snapshot.
    let ranked = &n.children;
    let width = req.chart_width.unwrap_or(800).clamp(240, 4000) as f64;
    // Only truly small children belong in Other folders: a branch that
    // occupies ~5% of a narrow 240px bar is still meaningful and navigable.
    // Use a 12px visual threshold rather than grouping substantial branches.
    let threshold = n.total_bytes.max(1) as f64 * (12.0 / width).max(0.012);
    let prominent: Vec<usize> = ranked
        .iter()
        .take(7)
        .copied()
        .filter(|k| s.nodes[*k].total_bytes as f64 >= threshold)
        .collect();
    let mut segments: Vec<Value> = prominent.iter().map(|k| node_json(s, *k)).collect();
    let small_count = ranked.len() - prominent.len();
    if small_count > 0 {
        let prominent_bytes: u64 = prominent.iter().map(|k| s.nodes[*k].total_bytes).sum();
        let small_bytes = n.total_bytes - n.own_bytes - n.direct_bytes - prominent_bytes;
        segments.push(json!({"type":"others","allocated_bytes":small_bytes,"count":small_count}));
    }
    let query = req.query.as_deref().unwrap_or("").to_lowercase();
    children.retain(|key| match key {
        Some(k) => {
            (!req.others.unwrap_or(false) || !prominent.contains(k))
                && (query.is_empty()
                    || String::from_utf8_lossy(&s.nodes[*k].name)
                        .to_lowercase()
                        .contains(&query))
        }
        None => {
            !req.directories_only.unwrap_or(false)
                && !req.others.unwrap_or(false)
                && query.is_empty()
        }
    });
    let offset = req.offset.unwrap_or(0).min(children.len());
    let end = offset.saturating_add(limit).min(children.len());
    let page: Vec<Value> = children[offset..end].iter().map(|key| match key {
        Some(k) => node_json(s, *k),
        None => json!({"type":"files","name":"Direct entries","allocated_bytes":n.direct_bytes,"entries":n.direct_entries}),
    }).collect();
    let mut ancestors = vec![];
    let mut cursor = Some(id);
    while let Some(k) = cursor {
        ancestors.push(json!({"node_id":k,"name":if k == 0 { s.root.to_string_lossy().into_owned() } else { String::from_utf8_lossy(&s.nodes[k].name).into_owned() },"name_hex":scan::hex(&s.nodes[k].name)}));
        cursor = s.nodes[k].parent;
    }
    ancestors.reverse();
    Ok(
        json!({"scan_id":req.scan_id,"node":node_json(s,id),"path":String::from_utf8_lossy(&s.path_bytes(id)),
        "path_hex":scan::hex(&s.path_bytes(id)),"root_hex":scan::hex(s.root.as_os_str().as_encoded_bytes()),
        "breadcrumbs":ancestors,"children":page,"segments":segments,"directory_count":n.children.len(),"chart_width":width,"offset":offset,"limit":limit,
        "total_children":children.len(),"next_offset":if end < children.len() { Some(end) } else { None },
        "sort":sort,"file_detail":"aggregated","directory_detail":"retained"}),
    )
}

/// Consumes overlong frames without retaining them. EOF needs no final newline.
pub fn read_frame(reader: &mut impl BufRead) -> io::Result<Option<Result<Vec<u8>, &'static str>>> {
    let mut line = vec![];
    let mut over = false;
    loop {
        let buf = reader.fill_buf()?;
        if buf.is_empty() {
            return if over {
                Ok(Some(Err("frame_too_large")))
            } else if line.is_empty() {
                Ok(None)
            } else {
                Ok(Some(Ok(line)))
            };
        }
        let count = buf
            .iter()
            .position(|b| *b == b'\n')
            .map(|n| n + 1)
            .unwrap_or(buf.len());
        let ended = buf[count - 1] == b'\n';
        if !over && line.len() + count <= MAX_INPUT {
            line.extend_from_slice(&buf[..count]);
        } else {
            over = true;
            line.clear();
        }
        reader.consume(count);
        if ended {
            return Ok(Some(if over {
                Err("frame_too_large")
            } else {
                Ok(line)
            }));
        }
    }
}
fn emit(writer: &mut impl Write, value: Value) -> io::Result<()> {
    let mut bytes = serde_json::to_vec(&value)?;
    if bytes.len() > MAX_OUTPUT {
        bytes = serde_json::to_vec(&error(
            value.get("id").cloned().unwrap_or(Value::Null),
            "response_too_large",
        ))?;
    }
    writer.write_all(&bytes)?;
    writer.write_all(b"\n")?;
    writer.flush()
}
pub fn run() -> io::Result<()> {
    // Bounded input queue prevents an eager client from retaining unlimited requests.
    let (tx, rx) = mpsc::sync_channel(8);
    thread::spawn(move || {
        let stdin = io::stdin();
        let mut input = stdin.lock();
        while let Ok(Some(frame)) = read_frame(&mut input) {
            if tx.send(frame).is_err() {
                break;
            }
        }
    });
    let mut engine = Engine::new();
    let stdout = io::stdout();
    let mut output = stdout.lock();
    let mut last_progress = Instant::now();
    loop {
        for value in engine.poll() {
            emit(&mut output, value)?;
        }
        match rx.recv_timeout(Duration::from_millis(25)) {
            Ok(Ok(line)) => {
                for value in engine.handle_line(&line) {
                    emit(&mut output, value)?;
                }
            }
            Ok(Err(code)) => emit(&mut output, error(Value::Null, code))?,
            Err(mpsc::RecvTimeoutError::Disconnected) => break,
            Err(mpsc::RecvTimeoutError::Timeout) => (),
        }
        if engine.closed {
            break;
        }
        if last_progress.elapsed() >= Duration::from_millis(250) {
            if let Some(value) = engine.progress_event() {
                emit(&mut output, value)?;
            }
            last_progress = Instant::now();
        }
    }
    Ok(())
}
