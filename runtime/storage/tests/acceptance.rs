use endless_storage::ipc::{self, Engine, Request};
use endless_storage::scan::{self, Options, Progress, ScanError, Snapshot};
use serde_json::{Value, json};
use std::fs::{self, File};
use std::io::{BufRead, BufReader, Write};
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::{MetadataExt, symlink};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::time::{Duration, Instant};

static SERIAL: AtomicU64 = AtomicU64::new(0);
struct Fixture(PathBuf);
impl Fixture {
    fn new() -> Self {
        let p = std::env::temp_dir().join(format!(
            "endless-storage-test-{}-{}",
            std::process::id(),
            SERIAL.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&p).unwrap();
        Self(p)
    }
    fn dir(&self, name: &str) -> PathBuf {
        let p = self.0.join(name);
        fs::create_dir_all(&p).unwrap();
        p
    }
    fn file(&self, name: &str, size: usize) -> PathBuf {
        let p = self.0.join(name);
        fs::write(&p, vec![b'x'; size]).unwrap();
        p
    }
    fn scan(&self, opts: Options) -> Snapshot {
        scan::scan(
            &self.0,
            &opts,
            &AtomicBool::new(false),
            &Progress::default(),
        )
        .unwrap()
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.0).unwrap();
    }
}
fn blocks(p: &Path) -> u64 {
    fs::symlink_metadata(p).unwrap().blocks() * 512
}
fn req(v: Value) -> Request {
    ipc::parse(v.to_string().as_bytes()).unwrap()
}
fn request(engine: &mut Engine, v: Value) -> Vec<Value> {
    engine.handle_line(v.to_string().as_bytes())
}
fn wait(engine: &mut Engine) -> Vec<Value> {
    let start = Instant::now();
    loop {
        let events = engine.poll();
        if !events.is_empty() {
            return events;
        }
        assert!(
            start.elapsed() < Duration::from_secs(10),
            "worker timed out"
        );
        std::thread::sleep(Duration::from_millis(1));
    }
}

#[test]
fn branches_and_browse_use_snapshot_after_fixture_removed() {
    let f = Fixture::new();
    f.dir("small");
    f.dir("medium/nested");
    f.dir("large");
    f.file("small/a", 4096);
    f.file("medium/nested/b", 32768);
    f.file("large/c", 131072);
    let s = f.scan(Options::default());
    let small = s.lookup(b"small").unwrap();
    let medium = s.lookup(b"medium").unwrap();
    let large = s.lookup(b"large").unwrap();
    assert!(s.nodes[small].total_bytes < s.nodes[medium].total_bytes);
    assert!(s.nodes[medium].total_bytes < s.nodes[large].total_bytes);
    // Move the fixture away: browsing may neither stat nor enumerate it again.
    let moved = f.0.with_extension("moved");
    fs::rename(&f.0, &moved).unwrap();
    let page = ipc::browse(
        &s,
        &req(json!({"id":"browse","action":"browse","path":"medium/nested"})),
    )
    .unwrap();
    assert_eq!(page["breadcrumbs"].as_array().unwrap().len(), 3);
    assert_eq!(
        page["node"]["direct_files_bytes"],
        blocks(&moved.join("medium/nested/b"))
    );
    assert_eq!(page["directory_detail"], "retained");
    fs::rename(moved, &f.0).unwrap();
}

#[test]
fn sparse_zero_symlink_socket_and_hardlinks_match_gnu_du() {
    let f = Fixture::new();
    f.dir("z");
    f.dir("a/nested");
    let original = f.file("z/hard", 131072);
    fs::hard_link(&original, f.0.join("a/hard")).unwrap();
    f.file("empty", 0);
    let sparse = File::create(f.0.join("sparse")).unwrap();
    sparse.set_len(128 * 1024 * 1024).unwrap();
    let outside = Fixture::new();
    outside.file("private", 1024 * 1024);
    symlink(&outside.0, f.0.join("outside-link")).unwrap();
    symlink(".", f.0.join("loop")).unwrap();
    let _socket = std::os::unix::net::UnixListener::bind(f.0.join("socket")).unwrap();
    let s = f.scan(Options::default());
    assert_eq!(s.nodes.len(), 4);
    assert_eq!(s.nodes[s.lookup(b"z").unwrap()].direct_bytes, 0);
    assert_eq!(
        s.nodes[s.lookup(b"a").unwrap()].direct_bytes,
        blocks(&original)
    );
    let direct = blocks(&f.0.join("sparse"))
        + blocks(&f.0.join("empty"))
        + blocks(&f.0.join("outside-link"))
        + blocks(&f.0.join("loop"))
        + blocks(&f.0.join("socket"));
    assert_eq!(s.nodes[0].direct_bytes, direct);
    assert!(blocks(&f.0.join("sparse")) < 128 * 1024 * 1024);
    let du = Command::new("du")
        .args(["-sx", "-B1", "--"])
        .arg(&f.0)
        .output()
        .expect("GNU du required for acceptance");
    assert!(du.status.success());
    let bytes: u64 = String::from_utf8(du.stdout)
        .unwrap()
        .split_whitespace()
        .next()
        .unwrap()
        .parse()
        .unwrap();
    assert_eq!(s.nodes[0].total_bytes, bytes);
}

#[test]
fn boundaries_include_same_device_bind_and_explicit_root_is_allowed() {
    let f = Fixture::new();
    let mounted = f.dir("bind/child");
    f.file("bind/child/data", 65536);
    f.dir("keep");
    let file_mount = f.file("file-bind", 65536);
    let opts = Options {
        boundaries: Some([f.0.join("bind"), file_mount].into()),
        ..Options::default()
    };
    let s = f.scan(opts);
    let bind = s.lookup(b"bind").unwrap();
    assert_eq!(s.nodes[bind].exclusion, Some("mount_boundary"));
    assert_eq!(s.nodes[bind].total_bytes, 0);
    assert_eq!(s.nodes[0].excluded_entries, 1);
    assert!(s.lookup(b"bind/child").is_none());
    let explicit = scan::scan(
        &mounted,
        &Options {
            boundaries: Some([mounted.clone()].into()),
            ..Options::default()
        },
        &AtomicBool::new(false),
        &Progress::default(),
    )
    .unwrap();
    assert!(explicit.nodes[0].total_bytes >= 65536);
    let parsed = scan::mount_boundaries(b"42 1 8:1 / /a\\040b rw - ext4 /dev/test rw\n43 1 8:1 /bind /other rw - ext4 /dev/test rw\n");
    assert!(parsed.contains(Path::new("/a b")));
    assert!(parsed.contains(Path::new("/other")));
}

#[test]
fn permission_io_and_depth_errors_propagate_without_losing_siblings() {
    let f = Fixture::new();
    f.dir("denied/secret");
    f.dir("io/secret");
    f.dir("good/deep/child");
    f.file("good/data", 8192);
    let opts = Options {
        max_depth: Some(2),
        faults: [
            (f.0.join("denied"), libc::EACCES),
            (f.0.join("io"), libc::EIO),
        ]
        .into(),
        ..Options::default()
    };
    let s = f.scan(opts);
    assert_eq!(s.nodes[0].subtree_issues, 3);
    assert_eq!(
        s.nodes[s.lookup(b"denied").unwrap()].issues[0].errno,
        Some(libc::EACCES)
    );
    assert_eq!(
        s.nodes[s.lookup(b"io").unwrap()].issues[0].errno,
        Some(libc::EIO)
    );
    assert!(s.nodes[s.lookup(b"good").unwrap()].total_bytes >= 8192);
    assert_eq!(
        s.nodes[s.lookup(b"good/deep/child").unwrap()].issues[0].code,
        "depth_limit"
    );
}

#[test]
fn raw_names_navigation_pagination_and_escaping() {
    let f = Fixture::new();
    let raw = b"bad-\xff\n\"";
    fs::create_dir(f.0.join(std::ffi::OsStr::from_bytes(raw))).unwrap();
    for name in ["alpha", "beta", "gamma"] {
        f.dir(name);
    }
    let s = f.scan(Options::default());
    let first = ipc::browse(
        &s,
        &req(json!({"id":"b","action":"browse","sort":"name","limit":2})),
    )
    .unwrap();
    assert_eq!(first["total_children"], 4);
    assert_eq!(first["next_offset"], 2);
    assert_eq!(first["children"][0]["name"], "alpha");
    let page = ipc::browse(
        &s,
        &req(json!({"id":"b","action":"browse","sort":"name","offset":2,"limit":2})),
    )
    .unwrap();
    assert_eq!(page["next_offset"], Value::Null);
    let raw_browse = ipc::browse(
        &s,
        &req(json!({"id":"b","action":"browse","path_hex":scan::hex(raw)})),
    )
    .unwrap();
    assert_eq!(raw_browse["node"]["name_hex"], scan::hex(raw));
    let serialized = serde_json::to_string(&raw_browse).unwrap();
    assert!(!serialized.contains('\n'));
    assert!(serialized.contains("\\n\\\""));
    assert_eq!(scan::unhex(&scan::hex(raw)).unwrap(), raw);
    assert!(
        ipc::browse(
            &s,
            &req(json!({"id":"b","action":"browse","path":"../escape"}))
        )
        .is_err()
    );
}

#[test]
fn engine_status_cancel_supersession_and_no_partial_snapshot() {
    let f = Fixture::new();
    f.dir("child");
    f.file("child/a", 65536);
    let mut e = Engine::new();
    let a = request(&mut e, json!({"id":"A","action":"scan","root":f.0}));
    let aid = a[0]["data"]["scan_id"].clone();
    let status = request(&mut e, json!({"id":"s","action":"status"}));
    assert_eq!(status[0]["data"]["scan_id"], aid);
    // No poll yet: even an already finished worker cannot publish after cancellation.
    request(
        &mut e,
        json!({"id":"cancel","action":"cancel","scan_id":aid}),
    );
    let done = wait(&mut e);
    assert_eq!(done[0]["state"], "aborted");
    let b = request(&mut e, json!({"id":"b","action":"browse","scan_id":aid}));
    assert_eq!(b[0]["error"]["code"], "snapshot_not_ready");
    let a = request(&mut e, json!({"id":"A2","action":"scan","root":f.0}));
    let old = a[0]["data"]["scan_id"].clone();
    let b = request(&mut e, json!({"id":"B","action":"scan","root":f.0}));
    assert_eq!(b[0]["state"], "aborted");
    assert_eq!(b[0]["data"]["reason"], "superseded");
    let bid = b[1]["data"]["scan_id"].clone();
    assert_ne!(old, bid);
    let stale = request(&mut e, json!({"id":"old","action":"cancel","scan_id":old}));
    assert_eq!(stale[0]["error"]["code"], "stale_scan");
    let done = wait(&mut e);
    assert_eq!(done[0]["scan_id"], bid);
    assert_eq!(done[0]["state"], "finished");
    let browse = request(
        &mut e,
        json!({"id":"browse","action":"browse","scan_id":bid,"path":"child"}),
    );
    assert_eq!(browse[0]["ok"], true);
}

#[test]
fn cancellation_works_from_another_thread() {
    let f = Fixture::new();
    f.dir("a");
    let cancel = AtomicBool::new(false);
    let progress = Progress::default();
    std::thread::scope(|scope| {
        let handle = scope.spawn(|| {
            cancel.store(true, Ordering::Relaxed);
        });
        handle.join().unwrap();
        assert!(matches!(
            scan::scan(&f.0, &Options::default(), &cancel, &progress),
            Err(ScanError::Cancelled)
        ));
    });
}

#[test]
fn invalid_roots_and_symlink_components_do_not_traverse() {
    let f = Fixture::new();
    f.file("file", 1);
    f.dir("real");
    symlink("real", f.0.join("link")).unwrap();
    for path in [
        f.0.join("missing"),
        f.0.join("file"),
        f.0.join("link"),
        f.0.join("link/child"),
        PathBuf::from("relative"),
    ] {
        assert!(matches!(
            scan::scan(
                &path,
                &Options::default(),
                &AtomicBool::new(false),
                &Progress::default()
            ),
            Err(ScanError::Failed(..))
        ));
    }
}

#[test]
fn malformed_and_oversized_frames_are_recoverable() {
    let mut e = Engine::new();
    for line in [
        b"{".as_slice(),
        b"null",
        b"[]",
        b"{\"id\":3,\"action\":\"status\"}",
        b"{\"id\":\"x\",\"action\":\"status\",\"typo\":1}",
    ] {
        assert_eq!(e.handle_line(line)[0]["error"]["code"], "invalid_request");
    }
    assert_eq!(
        request(&mut e, json!({"id":"u","action":"wat"}))[0]["error"]["code"],
        "unknown_action"
    );
    assert_eq!(
        request(&mut e, json!({"id":"h","action":"scan","root_hex":"ffx"}))[0]["error"]["code"],
        "invalid_hex"
    );
    let mut frames = vec![b'x'; ipc::MAX_INPUT + 1];
    frames.extend_from_slice(b"\n{\"id\":\"ok\",\"action\":\"status\"}\n");
    let mut input = std::io::Cursor::new(frames);
    assert_eq!(
        ipc::read_frame(&mut input).unwrap().unwrap(),
        Err("frame_too_large")
    );
    assert!(ipc::parse(&ipc::read_frame(&mut input).unwrap().unwrap().unwrap()).is_ok());
    assert!(ipc::read_frame(&mut input).unwrap().is_none());
    assert_eq!(
        request(&mut e, json!({"id":"s","action":"status"}))[0]["ok"],
        true
    );
}

#[test]
fn subprocess_stdout_is_jsonlines_and_remains_interactive() {
    let f = Fixture::new();
    f.dir("a");
    f.file("a/data", 4096);
    let mut child = Command::new(env!("CARGO_BIN_EXE_endless-storage"))
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    let mut input = child.stdin.take().unwrap();
    let mut output = BufReader::new(child.stdout.take().unwrap());
    writeln!(input, "{{malformed").unwrap();
    writeln!(input, "{}", json!({"id":"scan","action":"scan","root":f.0})).unwrap();
    writeln!(input, "{}", json!({"id":"status","action":"status"})).unwrap();
    let mut ack = false;
    let mut status = false;
    let mut completed = false;
    let mut sid = Value::Null;
    while !(ack && status && completed) {
        let mut line = String::new();
        assert!(output.read_line(&mut line).unwrap() > 0);
        assert!(line.len() <= ipc::MAX_OUTPUT + 1);
        let v: Value = serde_json::from_str(&line).unwrap();
        if v["id"] == "scan" {
            ack = true;
            sid = v["data"]["scan_id"].clone();
        }
        if v["id"] == "status" {
            status = true;
        }
        if v["event"] == "completed" {
            assert_eq!(v["state"], "finished");
            completed = true;
        }
    }
    writeln!(
        input,
        "{}",
        json!({"id":"browse","action":"browse","scan_id":sid})
    )
    .unwrap();
    let mut line = String::new();
    output.read_line(&mut line).unwrap();
    let v: Value = serde_json::from_str(&line).unwrap();
    assert_eq!(v["ok"], true);
    writeln!(input, "{{\"id\":\"close\",\"action\":\"close\"}}").unwrap();
    let mut line = String::new();
    output.read_line(&mut line).unwrap();
    assert_eq!(serde_json::from_str::<Value>(&line).unwrap()["id"], "close");
    assert!(child.wait().unwrap().success());
}

#[test]
#[ignore = "synthetic fixture benchmark; run explicitly with --ignored --nocapture"]
fn benchmark_fixture() {
    let f = Fixture::new();
    for i in 0..100 {
        f.dir(&format!("d{i}/nested"));
        for j in 0..100 {
            f.file(&format!("d{i}/nested/f{j}"), 32);
        }
    }
    let t = Instant::now();
    let s = f.scan(Options::default());
    eprintln!(
        "fixture: 10000 files, {} directories, {} allocated bytes, {} ms (warm cache, debug/release depends on invocation)",
        s.nodes.len(),
        s.nodes[0].total_bytes,
        t.elapsed().as_millis()
    );
    assert_eq!(s.nodes.len(), 201);
}

#[test]
fn warnings_are_global_counts_and_local_browse_details() {
    let f = Fixture::new();
    f.dir("sensitive-dir");
    f.dir("healthy");
    let mut e = Engine::with_options(Options {
        faults: [(f.0.join("sensitive-dir"), libc::EACCES)].into(),
        ..Options::default()
    });
    let ack = request(&mut e, json!({"id":"scan","action":"scan","root":f.0}));
    let sid = ack[0]["data"]["scan_id"].clone();
    let done = wait(&mut e);
    assert_eq!(done[0]["state"], "finished-with-warnings");
    assert_eq!(done[0]["data"]["issue_count"], 1);
    assert!(!done[0].to_string().contains("sensitive-dir"));
    assert!(
        !done[0]
            .to_string()
            .contains(&f.0.to_string_lossy().to_string())
    );
    let browse = request(
        &mut e,
        json!({"id":"b","action":"browse","scan_id":sid,"path":"sensitive-dir"}),
    );
    assert_eq!(
        browse[0]["data"]["node"]["issues"][0]["errno"],
        libc::EACCES
    );
}

#[test]
fn failed_scan_has_no_browseable_snapshot_and_ack_precedes_completion() {
    let f = Fixture::new();
    let mut e = Engine::new();
    let ack = request(
        &mut e,
        json!({"id":"missing","action":"scan","root":f.0.join("absent")}),
    );
    assert_eq!(ack.len(), 1);
    assert_eq!(ack[0]["ok"], true);
    let sid = ack[0]["data"]["scan_id"].clone();
    let done = wait(&mut e);
    assert_eq!(done[0]["state"], "failed");
    assert_eq!(done[0]["data"]["error"]["code"], "root_open_failed");
    assert_eq!(
        request(&mut e, json!({"id":"b","action":"browse","scan_id":sid}))[0]["error"]["code"],
        "snapshot_not_ready"
    );
}

#[test]
fn many_files_have_constant_retained_directory_count_and_active_cancellation() {
    let f = Fixture::new();
    f.dir("data");
    for i in 0..4000 {
        f.file(&format!("data/f{i}"), 0);
    }
    let progress = Progress::default();
    let cancel = AtomicBool::new(false);
    std::thread::scope(|scope| {
        let scan = scope.spawn(|| scan::scan(&f.0, &Options::default(), &cancel, &progress));
        let start = Instant::now();
        // Observe the worker from another thread during metadata enumeration.
        while progress.files.load(Ordering::Relaxed) == 0 {
            assert!(start.elapsed() < Duration::from_secs(10));
            std::thread::yield_now();
        }
        cancel.store(true, Ordering::Relaxed);
        assert!(matches!(scan.join().unwrap(), Err(ScanError::Cancelled)));
    });
    let s = f.scan(Options::default());
    assert_eq!(s.nodes.len(), 2);
    assert_eq!(s.nodes[1].direct_entries, 4000);
    assert_eq!(s.execution.hardlinks_retained, 0);
    assert!(s.nodes[1].issues.is_empty());
}

#[test]
fn replacement_queue_coalesces_and_cancel_of_queued_job_is_terminal() {
    let f = Fixture::new();
    let mut e = Engine::new();
    request(&mut e, json!({"id":"A","action":"scan","root":f.0}));
    request(&mut e, json!({"id":"B","action":"scan","root":f.0}));
    let c = request(&mut e, json!({"id":"C","action":"scan","root":f.0}));
    assert_eq!(c[0]["request_id"], "B");
    assert_eq!(c[0]["data"]["reason"], "superseded");
    let cid = c[1]["data"]["scan_id"].clone();
    let cancelled = request(
        &mut e,
        json!({"id":"cancel","action":"cancel","scan_id":cid}),
    );
    assert_eq!(cancelled[0]["state"], "aborted");
    // Drain obsolete worker; it must never publish A or B as complete.
    for _ in 0..30 {
        assert!(e.poll().is_empty());
        std::thread::sleep(Duration::from_millis(1));
    }
    assert_eq!(
        request(&mut e, json!({"id":"s","action":"status"}))[0]["data"]["state"],
        "aborted"
    );
}

#[test]
fn chart_uses_all_children_and_others_remains_browsable_across_pages() {
    let f = Fixture::new();
    f.dir("big");
    f.file("big/file", 1024 * 1024);
    for i in 0..170 {
        f.dir(&format!("tiny{i:03}"));
    }
    f.file("direct", 8192);
    let s = f.scan(Options::default());
    let first = ipc::browse(
        &s,
        &req(json!({"id":"first","action":"browse",
        "directories_only":true,"limit":60,"chart_width":1200})),
    )
    .unwrap();
    assert_eq!(first["total_children"], 171);
    assert_eq!(first["children"].as_array().unwrap().len(), 60);
    let segments = first["segments"].as_array().unwrap();
    assert_eq!(segments[0]["name"], "big");
    let others = segments.iter().find(|v| v["type"] == "others").unwrap();
    assert_eq!(others["count"], 170);
    let tiny_bytes: u64 = s.nodes[0]
        .children
        .iter()
        .filter(|&&i| s.nodes[i].name.starts_with(b"tiny"))
        .map(|&i| s.nodes[i].total_bytes)
        .sum();
    assert_eq!(others["allocated_bytes"], tiny_bytes);
    let measured: u64 = segments
        .iter()
        .map(|v| v["allocated_bytes"].as_u64().unwrap())
        .sum();
    assert_eq!(
        measured + s.nodes[0].own_bytes + s.nodes[0].direct_bytes,
        s.nodes[0].total_bytes
    );
    let last = ipc::browse(
        &s,
        &req(json!({"id":"last","action":"browse",
        "others":true,"offset":120,"limit":60,"chart_width":1200})),
    )
    .unwrap();
    assert_eq!(last["total_children"], 170);
    assert_eq!(last["children"].as_array().unwrap().len(), 50);
    assert!(last["next_offset"].is_null());
    assert_eq!(last["segments"], first["segments"]);
    let filtered = ipc::browse(
        &s,
        &req(json!({"id":"filter","action":"browse",
        "query":"TINY16","sort":"name","directories_only":true,"chart_width":1200})),
    )
    .unwrap();
    assert_eq!(filtered["total_children"], 10);
    assert_eq!(filtered["children"][0]["name"], "tiny160");
    assert_eq!(filtered["segments"], first["segments"]);
}

fn parallel_fixture() -> Fixture {
    let f = Fixture::new();
    for b in 0..24 {
        for depth in ["a", "a/nested"] {
            f.dir(&format!("b{b:02}/{depth}"));
            for file in 0..12 {
                f.file(&format!("b{b:02}/{depth}/f{file:02}"), 17 + b * file);
            }
        }
    }
    let original = f.file("b23/a/shared", 32768);
    for branch in [0, 1, 12, 17] {
        fs::hard_link(&original, f.0.join(format!("b{branch:02}/a/nested/shared"))).unwrap();
    }
    let sparse = File::create(f.0.join("b03/a/sparse")).unwrap();
    sparse.set_len(1 << 24).unwrap();
    symlink("../../../outside", f.0.join("b04/a/link")).unwrap();
    let raw = std::ffi::OsStr::from_bytes(b"raw-\xff");
    fs::create_dir(f.0.join(raw)).unwrap();
    f
}
type MeasuredNode = (u64, u64, u64, u64, u64, Option<&'static str>);
fn measured_tree(s: &Snapshot) -> std::collections::BTreeMap<Vec<u8>, MeasuredNode> {
    (0..s.nodes.len())
        .map(|id| {
            let n = &s.nodes[id];
            (
                s.path_bytes(id),
                (
                    n.total_bytes,
                    n.own_bytes,
                    n.direct_bytes,
                    n.direct_entries,
                    n.subtree_issues,
                    n.exclusion,
                ),
            )
        })
        .collect()
}

#[test]
fn parallel_hardlinks_mounts_totals_names_and_pages_are_deterministic() {
    let f = parallel_fixture();
    let opts = |workers| Options {
        workers: Some(workers),
        boundaries: Some([f.0.join("b05/a/nested"), f.0.join("b22/a/f00")].into()),
        ..Options::default()
    };
    let all = f.scan(Options {
        workers: Some(4),
        ..Options::default()
    });
    let du = Command::new("du")
        .args(["-sx", "-B1", "--"])
        .arg(&f.0)
        .output()
        .unwrap();
    assert!(du.status.success());
    let du_bytes: u64 = String::from_utf8(du.stdout)
        .unwrap()
        .split_whitespace()
        .next()
        .unwrap()
        .parse()
        .unwrap();
    assert_eq!(all.nodes[0].total_bytes, du_bytes);
    let baseline = f.scan(opts(1));
    let expected = measured_tree(&baseline);
    assert_eq!(baseline.execution.hardlinks_retained, 1);
    assert_eq!(baseline.summary.excluded_count, 2);
    assert_eq!(baseline.summary.unreadable_count, 0);
    // Only the lexical owner receives the global inode's blocks.
    let winner = baseline.lookup(b"b00/a/nested").unwrap();
    let loser = baseline.lookup(b"b23/a").unwrap();
    assert!(baseline.nodes[winner].direct_bytes >= blocks(&f.0.join("b23/a/shared")));
    let ordinary_loser: u64 = (0..12)
        .map(|i| blocks(&f.0.join(format!("b23/a/f{i:02}"))))
        .sum();
    assert_eq!(baseline.nodes[loser].direct_bytes, ordinary_loser);
    for workers in [1, 2, 4, 4, 2] {
        let progress = Progress::default();
        let s = scan::scan(&f.0, &opts(workers), &AtomicBool::new(false), &progress).unwrap();
        assert_eq!(
            progress.bytes.load(Ordering::Relaxed),
            s.nodes[0].total_bytes
        );
        assert_eq!(
            progress.files.load(Ordering::Relaxed),
            s.nodes.iter().map(|n| n.direct_entries).sum::<u64>()
        );
        assert_eq!(
            progress.directories.load(Ordering::Relaxed),
            s.nodes.len() as u64
        );
        assert_eq!(measured_tree(&s), expected);
        assert!(s.execution.workers_used <= workers);
        if workers > 1 {
            assert!(s.execution.workers_used > 1);
        }
        assert!(s.execution.queue_peak <= workers * 2);
        let mut offset = Some(0);
        let mut names = vec![];
        while let Some(at) = offset {
            let page = ipc::browse(&s, &req(json!({"id":"p","action":"browse","sort":"size_desc","offset":at,"limit":7,"directories_only":true}))).unwrap();
            assert!(page["children"].as_array().unwrap().len() <= 7);
            names.extend(
                page["children"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|v| v["name_hex"].as_str().unwrap().to_owned()),
            );
            offset = page["next_offset"].as_u64().map(|x| x as usize);
        }
        let reference = ipc::browse(
            &baseline,
            &req(json!({"id":"all","action":"browse","limit":128,"directories_only":true})),
        )
        .unwrap();
        let expected_names: Vec<_> = reference["children"]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v["name_hex"].as_str().unwrap().to_owned())
            .collect();
        assert_eq!(names, expected_names);
        let raw = ipc::browse(
            &s,
            &req(json!({"id":"raw","action":"browse","path_hex":scan::hex(b"raw-\xff")})),
        )
        .unwrap();
        assert_eq!(raw["node"]["name_hex"], scan::hex(b"raw-\xff"));
    }
}

#[test]
fn small_tree_creates_no_helpers_and_workers_are_validated() {
    let f = Fixture::new();
    f.dir("a/b");
    f.file("a/b/x", 0);
    for workers in [1, 2, 4] {
        let s = f.scan(Options {
            workers: Some(workers),
            ..Options::default()
        });
        assert_eq!(s.execution.workers_used, 1);
    }
    for workers in [0, 5] {
        assert!(matches!(
            scan::scan(
                &f.0,
                &Options {
                    workers: Some(workers),
                    ..Options::default()
                },
                &AtomicBool::new(false),
                &Progress::default()
            ),
            Err(ScanError::Failed("invalid_workers", _))
        ));
        let mut e = Engine::new();
        assert_eq!(
            request(
                &mut e,
                json!({"id":"bad","action":"scan","root":f.0,"workers":workers})
            )[0]["error"]["code"],
            "invalid_workers"
        );
    }
}

#[test]
fn observed_changes_do_not_become_unreadable_warnings() {
    use scan::ScanPhase;
    use std::sync::Arc;
    let f = Fixture::new();
    f.dir("changing");
    let root = f.0.clone();
    let hook = Arc::new(move |path: &Path, phase| {
        if path == root.join("changing") && phase == ScanPhase::BeforeDirectoryFinish {
            fs::write(path.join("new-entry-after-enumeration"), b"changed").unwrap();
        }
    });
    let mut e = Engine::with_options(Options {
        workers: Some(4),
        visit_hook: Some(hook),
        ..Options::default()
    });
    let ack = request(&mut e, json!({"id":"s","action":"scan","root":f.0}));
    let sid = ack[0]["data"]["scan_id"].clone();
    let done = wait(&mut e);
    let summary = &done[0]["data"];
    assert_eq!(done[0]["state"], "finished");
    assert_eq!(summary["issue_count"], 1);
    assert_eq!(summary["unstable_entries"], 1);
    assert_eq!(summary["unreadable_count"], 0);
    assert_eq!(summary["coverage_incomplete"], false);
    assert_eq!(summary["coverage_uncertain"], true);
    assert_eq!(summary["changes_observed"], true);
    assert_eq!(summary["issue_codes"]["directory_changed"], 1);
    assert!(!done[0].to_string().contains("changing"));
    let page = request(
        &mut e,
        json!({"id":"b","action":"browse","scan_id":sid,"path":"changing"}),
    );
    let node = &page[0]["data"]["node"];
    assert_eq!(node["complete"], false); // Stability still matters to this conservative legacy flag.
    assert_eq!(node["coverage_incomplete"], false);
    assert_eq!(node["issues"][0]["category"], "unstable");
    assert_eq!(node["direct_entries"], 0);
}

#[test]
fn omissions_read_failures_and_mount_identity_failures_keep_coverage_warning() {
    let f = parallel_fixture();
    let mut e = Engine::with_options(Options {
        workers: Some(4),
        faults: [(f.0.join("b01/a"), libc::EACCES)].into(),
        entry_faults: [(f.0.join("b02/a/f00"), libc::ENOENT)].into(),
        read_faults: [(f.0.join("b03/a"), libc::EIO)].into(),
        mount_faults: [(f.0.join("b04/a"), libc::EIO)].into(),
        boundaries: Some([f.0.join("b05/a")].into()),
        ..Options::default()
    });
    request(&mut e, json!({"id":"s","action":"scan","root":f.0}));
    let done = wait(&mut e);
    let data = &done[0]["data"];
    assert_eq!(done[0]["state"], "finished-with-warnings");
    assert_eq!(data["unreadable_count"], 4);
    assert_eq!(data["unstable_entries"], 0);
    assert_eq!(data["excluded_count"], 1);
    assert_eq!(data["coverage_incomplete"], true);
    for code in [
        "open_directory",
        "stat_entry",
        "read_directory",
        "mount_identity_unavailable",
    ] {
        assert_eq!(data["issue_codes"][code], 1);
    }
}

#[test]
fn cancellation_at_scan_phases_discards_parallel_results() {
    use scan::ScanPhase;
    use std::sync::Arc;
    let f = parallel_fixture();
    for workers in [1, 2, 4] {
        for phase in [
            ScanPhase::DirectoryOpened,
            ScanPhase::BeforeDirectoryFinish,
            ScanPhase::BeforeFold,
        ] {
            let cancel = Arc::new(AtomicBool::new(false));
            let for_hook = cancel.clone();
            let root = f.0.clone();
            let hook = Arc::new(move |path: &Path, event| {
                if event == phase && (phase == ScanPhase::BeforeFold || path == root.join("b20/a"))
                {
                    for_hook.store(true, Ordering::Relaxed);
                }
            });
            let result = scan::scan(
                &f.0,
                &Options {
                    workers: Some(workers),
                    visit_hook: Some(hook),
                    ..Options::default()
                },
                &cancel,
                &Progress::default(),
            );
            assert!(matches!(result, Err(ScanError::Cancelled)));
        }
    }
}

#[test]
fn cached_chart_and_other_pages_are_stable_with_parallel_scan() {
    let f = Fixture::new();
    f.dir("big");
    f.file("big/file", 1 << 20);
    for i in 0..171 {
        f.dir(&format!("tiny{i:03}/nested"));
    }
    for workers in [1, 2, 4] {
        let s = f.scan(Options {
            workers: Some(workers),
            ..Options::default()
        });
        let mut at = Some(0);
        let mut ids = std::collections::HashSet::new();
        let mut segments = None;
        while let Some(offset) = at {
            let page = ipc::browse(&s, &req(json!({"id":"p","action":"browse","others":true,"offset":offset,"limit":29,"chart_width":1200}))).unwrap();
            let chart = page["segments"].clone();
            if let Some(ref expected) = segments {
                assert_eq!(chart, *expected);
            } else {
                segments = Some(chart);
            }
            for node in page["children"].as_array().unwrap() {
                assert!(ids.insert(node["node_id"].as_u64().unwrap()));
            }
            assert!(serde_json::to_vec(&page).unwrap().len() < ipc::MAX_OUTPUT);
            at = page["next_offset"].as_u64().map(|v| v as usize);
        }
        assert_eq!(ids.len(), 171);
    }
}

#[test]
fn ipc_remains_responsive_while_parallel_scan_is_blocked_and_superseded() {
    use scan::ScanPhase;
    use std::sync::{Arc, Mutex, mpsc};
    let f = parallel_fixture();
    let claimed = AtomicBool::new(false);
    let (entered_tx, entered_rx) = mpsc::sync_channel(1);
    let (release_tx, release_rx) = mpsc::sync_channel(1);
    let release_rx = Mutex::new(release_rx);
    let hook = Arc::new(move |path: &Path, phase| {
        if phase == ScanPhase::DirectoryOpened
            && path.ends_with("b20/a")
            && !claimed.swap(true, Ordering::Relaxed)
        {
            entered_tx.send(()).unwrap();
            release_rx
                .lock()
                .unwrap()
                .recv_timeout(Duration::from_secs(10))
                .unwrap();
        }
    });
    let mut e = Engine::with_options(Options {
        workers: Some(4),
        visit_hook: Some(hook),
        ..Options::default()
    });
    let a = request(&mut e, json!({"id":"A","action":"scan","root":f.0}));
    let aid = a[0]["data"]["scan_id"].clone();
    entered_rx.recv_timeout(Duration::from_secs(5)).unwrap();
    assert_eq!(
        request(&mut e, json!({"id":"status","action":"status"}))[0]["data"]["state"],
        "scanning"
    );
    assert_eq!(
        request(&mut e, json!({"id":"progress","action":"progress"}))[0]["ok"],
        true
    );
    assert_eq!(
        request(
            &mut e,
            json!({"id":"cancel","action":"cancel","scan_id":aid})
        )[0]["data"]["state"],
        "cancelling"
    );
    let b = request(
        &mut e,
        json!({"id":"B","action":"scan","root":f.0,"workers":2}),
    );
    assert_eq!(b[0]["request_id"], "A");
    assert_eq!(b[0]["state"], "aborted");
    let bid = b[1]["data"]["scan_id"].clone();
    assert_eq!(b[1]["data"]["state"], "queued");
    assert_eq!(
        request(
            &mut e,
            json!({"id":"stale","action":"cancel","scan_id":aid})
        )[0]["error"]["code"],
        "stale_scan"
    );
    release_tx.send(()).unwrap();
    let done = wait(&mut e);
    assert_eq!(done[0]["scan_id"], bid);
    assert_eq!(done[0]["state"], "finished");
    assert_eq!(done[0]["data"]["execution"]["workers_limit"], 2);
    assert!(
        done[0]["data"]["execution"]["workers_used"]
            .as_u64()
            .unwrap()
            <= 2
    );
}

#[test]
fn issue_histogram_does_not_truncate_with_local_samples() {
    let f = Fixture::new();
    f.dir("a");
    let mut faults = std::collections::HashMap::new();
    for i in 0..40 {
        let path = f.file(&format!("a/f{i:02}"), 0);
        faults.insert(path, libc::ENOENT);
    }
    let s = f.scan(Options {
        entry_faults: faults,
        ..Options::default()
    });
    assert_eq!(s.summary.unreadable_count, 40);
    assert_eq!(s.summary.issue_codes["stat_entry"], 40);
    let a = s.lookup(b"a").unwrap();
    assert_eq!(s.nodes[a].issues.len(), 16);
    let browse = ipc::browse(&s, &req(json!({"id":"b","action":"browse","node_id":a}))).unwrap();
    assert_eq!(browse["node"]["issue_samples_truncated"], true);
    assert_eq!(browse["node"]["subtree_unreadable_count"], 40);
}

#[test]
fn worker_panic_discards_snapshot_and_does_not_deadlock_helpers() {
    use scan::ScanPhase;
    use std::sync::Arc;
    let f = parallel_fixture();
    let hook = Arc::new(|path: &Path, phase| {
        if phase == ScanPhase::DirectoryOpened && path.ends_with("b20/a") {
            panic!("injected worker failure");
        }
    });
    let result = scan::scan(
        &f.0,
        &Options {
            workers: Some(4),
            visit_hook: Some(hook),
            ..Options::default()
        },
        &AtomicBool::new(false),
        &Progress::default(),
    );
    assert!(matches!(result, Err(ScanError::Failed("worker_failed", _))));
}

#[test]
fn unlinked_directory_is_coverage_loss_instead_of_metadata_only() {
    use scan::ScanPhase;
    use std::sync::Arc;
    let f = Fixture::new();
    f.dir("removed");
    f.dir("kept");
    let hook = Arc::new(|path: &Path, phase| {
        if phase == ScanPhase::BeforeDirectoryFinish && path.ends_with("removed") {
            fs::remove_dir(path).unwrap();
        }
    });
    let s = f.scan(Options {
        workers: Some(2),
        visit_hook: Some(hook),
        ..Options::default()
    });
    assert_eq!(s.summary.unreadable_count, 1);
    // Root can also observe its entry list changing. That is a separate observation.
    assert_eq!(s.summary.issue_codes["directory_removed"], 1);
    let removed = s.lookup(b"removed").unwrap();
    assert_eq!(s.nodes[removed].issues[0].category, "unreadable");
    assert_eq!(s.nodes[removed].unstable_entries, 0);
    assert!(s.lookup(b"kept").is_some());
}
