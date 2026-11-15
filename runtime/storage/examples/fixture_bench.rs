//! Reproducible, sequential warm-cache comparison using JSONL worker timing.
//! Arguments are executable paths, NEVER filesystem roots to scan.
use serde_json::{Value, json};
use std::fs;
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::time::Instant;

struct Fixture(PathBuf);
impl Drop for Fixture {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.0).unwrap();
    }
}
struct Session {
    child: Child,
    input: ChildStdin,
    output: BufReader<ChildStdout>,
    workers: Option<usize>,
    serial: usize,
}
impl Session {
    fn new(binary: &Path, workers: Option<usize>) -> Self {
        let mut child = Command::new(binary)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .spawn()
            .unwrap();
        Self {
            input: child.stdin.take().unwrap(),
            output: BufReader::new(child.stdout.take().unwrap()),
            child,
            workers,
            serial: 0,
        }
    }
    fn scan(&mut self, root: &Path) -> Value {
        self.serial += 1;
        let mut request = json!({"id":format!("bench-{}",self.serial),"action":"scan","root":root});
        if let Some(workers) = self.workers {
            request["workers"] = json!(workers);
        }
        writeln!(self.input, "{request}").unwrap();
        self.input.flush().unwrap();
        loop {
            let mut line = String::new();
            assert!(self.output.read_line(&mut line).unwrap() > 0);
            let value: Value = serde_json::from_str(&line).unwrap();
            assert_ne!(value["ok"], false, "{value}");
            if value["event"] == "completed" {
                assert_eq!(value["state"], "finished", "{value}");
                return value["data"].clone();
            }
        }
    }
    fn rss_kib(&self) -> u64 {
        let text = fs::read_to_string(format!("/proc/{}/status", self.child.id())).unwrap();
        text.lines()
            .find(|s| s.starts_with("VmHWM:"))
            .unwrap()
            .split_whitespace()
            .nth(1)
            .unwrap()
            .parse()
            .unwrap()
    }
}
impl Drop for Session {
    fn drop(&mut self) {
        writeln!(self.input, "{{\"id\":\"close\",\"action\":\"close\"}}").unwrap();
        self.child.wait().unwrap();
    }
}
fn main() {
    let args: Vec<_> = std::env::args_os().collect();
    assert!(
        args.len() == 2 || args.len() == 3,
        "usage: fixture_bench NEW_BINARY [BASELINE_BINARY]"
    );
    for (fixture_index, (label, branches, depth, files)) in [
        ("small", 3, 2, 4),
        ("wide", 32, 4, 400),
        ("directory-heavy", 32, 48, 4),
    ]
    .into_iter()
    .enumerate()
    {
        let f = Fixture(std::env::temp_dir().join(format!(
            "endless-storage-bench-{}-{fixture_index}",
            std::process::id()
        )));
        fs::create_dir(&f.0).unwrap();
        for b in 0..branches {
            let mut path = f.0.join(format!("branch-{b:03}"));
            for d in 0..depth {
                path.push(format!("d{d:03}"));
                fs::create_dir_all(&path).unwrap();
                for file in 0..files {
                    fs::write(path.join(format!("f{file:04}")), []).unwrap();
                }
            }
        }
        let mut labels = vec!["new-1", "new-2", "new-4"];
        let mut sessions: Vec<_> = [1, 2, 4]
            .into_iter()
            .map(|w| Session::new(Path::new(&args[1]), Some(w)))
            .collect();
        if args.len() == 3 {
            labels.push("baseline");
            sessions.push(Session::new(Path::new(&args[2]), None));
        }
        let mut expected = None;
        for s in &mut sessions {
            let value = s.scan(&f.0);
            let total = value["total_bytes"].as_u64().unwrap();
            assert_eq!(value["directories_retained"], 1 + branches * (depth + 1));
            if let Some(expected) = expected {
                assert_eq!(total, expected);
            } else {
                expected = Some(total);
            }
        }
        let mut timings = vec![vec![]; sessions.len()];
        let mut executions = vec![Value::Null; sessions.len()];
        let started = Instant::now();
        // Rotate order to reduce systematic order bias. No scans run concurrently.
        for round in 0..9 {
            for slot in 0..sessions.len() {
                let i = (round + slot) % sessions.len();
                let value = sessions[i].scan(&f.0);
                assert_eq!(value["total_bytes"].as_u64().unwrap(), expected.unwrap());
                timings[i].push(value["elapsed_ms"].as_u64().unwrap());
                executions[i] = value["execution"].clone();
            }
        }
        println!(
            "fixture={label} files={} directories={} rounds=9 warmups=1/config; measurement=worker elapsed_ms, warm cache; batch_wall_ms={}",
            branches * depth * files,
            1 + branches * (depth + 1),
            started.elapsed().as_millis()
        );
        for i in 0..sessions.len() {
            timings[i].sort_unstable();
            println!(
                "  {} median_ms={} min_ms={} max_ms={} peak_rss_kib={} execution={}",
                labels[i],
                timings[i][4],
                timings[i][0],
                timings[i][8],
                sessions[i].rss_kib(),
                executions[i]
            );
        }
    }
}
