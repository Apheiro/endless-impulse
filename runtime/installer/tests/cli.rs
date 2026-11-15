//! Real executable, disposable fixtures only; no host service or desktop actions.
use endless_setup::{Category, Manifest, Ownership, PayloadFile, digest};
use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::path::PathBuf;
use std::process::{Command, Output, Stdio};
use tempfile::TempDir;

struct Cli {
    _temp: TempDir,
    sandbox: PathBuf,
    manifest: PathBuf,
}
impl Cli {
    fn new() -> Self {
        let temp = tempfile::Builder::new()
            .prefix("endless-cli-")
            .tempdir_in("/tmp")
            .unwrap();
        let sandbox = temp.path().join("sandbox");
        fs::create_dir(&sandbox).unwrap();
        fs::set_permissions(&sandbox, fs::Permissions::from_mode(0o700)).unwrap();
        let bundle = temp.path().join("bundle");
        fs::create_dir(&bundle).unwrap();
        fs::write(bundle.join("source"), "content").unwrap();
        let manifest = bundle.join("manifest.json");
        fs::write(
            &manifest,
            serde_json::to_vec(&Manifest {
                schema: 1,
                payload_version: "fixture-v1".into(),
                completeness: "subset".into(),
                dependencies: "not_implemented".into(),
                services: "not_implemented".into(),
                assets: vec![],
                files: vec![PayloadFile {
                    source: "source".into(),
                    category: Category::HyprConfig,
                    destination: "hyprland/example.lua".into(),
                    sha256: digest(b"content"),
                    ownership: Ownership::Managed,
                    mode: 0o644,
                }],
            })
            .unwrap(),
        )
        .unwrap();
        Self {
            _temp: temp,
            sandbox,
            manifest,
        }
    }
    fn command(&self) -> Command {
        let mut c = Command::new(env!("CARGO_BIN_EXE_endless-setup"));
        c.stdin(Stdio::null());
        c.env("HOME", self._temp.path().join("fake-home"));
        c
    }
    fn run(&self, action: &str, extras: &[&str]) -> Output {
        self.command()
            .arg(action)
            .arg("--sandbox")
            .arg(&self.sandbox)
            .arg("--manifest")
            .arg(&self.manifest)
            .arg("--json")
            .args(extras)
            .output()
            .unwrap()
    }
}
fn value(output: &Output) -> serde_json::Value {
    assert!(
        output.status.success(),
        "stderr: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    serde_json::from_slice(&output.stdout).unwrap()
}
#[test]
fn clean_idempotent_update_repair_and_uninstall_cli() {
    let f = Cli::new();
    assert_eq!(
        value(&f.run("install", &["--yes"]))["status"],
        "subset_applied"
    );
    assert_eq!(value(&f.run("install", &["--yes"]))["status"], "unchanged");
    let file = f.sandbox.join("config/hypr/hyprland/example.lua");
    fs::remove_file(&file).unwrap();
    value(&f.run("repair", &["--yes"]));
    assert_eq!(fs::read(&file).unwrap(), b"content");
    let mut manifest: Manifest = serde_json::from_slice(&fs::read(&f.manifest).unwrap()).unwrap();
    manifest.payload_version = "fixture-v2".into();
    manifest.files[0].destination = "hyprland/renamed.lua".into();
    fs::write(&f.manifest, serde_json::to_vec(&manifest).unwrap()).unwrap();
    value(&f.run("update", &["--yes"]));
    assert!(!file.exists());
    value(&f.run("uninstall", &["--yes"]));
    assert!(!f.sandbox.join("config/hypr/hyprland/renamed.lua").exists());
}
#[test]
fn plan_dry_run_doctor_and_unconfirmed_execute_do_not_write() {
    let f = Cli::new();
    let plan = value(&f.run("plan", &[]));
    assert_eq!(plan["operations"][0]["kind"], "create");
    value(&f.run("install", &["--dry-run"]));
    let doctor = value(&f.run("doctor", &[]));
    assert_eq!(doctor["sandbox"]["inventory_present"], false);
    assert!(!f.run("install", &[]).status.success());
    assert_eq!(fs::read_dir(&f.sandbox).unwrap().count(), 0);
}
#[test]
fn preexisting_conflicts_modified_preservation_and_original_restore_cli() {
    let f = Cli::new();
    let file = f.sandbox.join("config/hypr/hyprland/example.lua");
    fs::create_dir_all(file.parent().unwrap()).unwrap();
    fs::write(&file, "original").unwrap();
    assert!(!f.run("install", &["--yes"]).status.success());
    value(&f.run("install", &["--yes", "--allow-replace"]));
    value(&f.run("uninstall", &["--yes"]));
    assert_eq!(fs::read(&file).unwrap(), b"original");
    value(&f.run("install", &["--yes", "--allow-replace"]));
    fs::write(&file, "personal edit").unwrap();
    assert!(
        !f.run("repair", &["--yes", "--allow-replace"])
            .status
            .success()
    );
    value(&f.run("uninstall", &["--yes"]));
    assert_eq!(fs::read(file).unwrap(), b"personal edit");
}
#[test]
fn non_tty_help_version_and_tui_terminate_without_input() {
    let f = Cli::new();
    for flag in ["--help", "--version"] {
        let output = f.command().arg(flag).output().unwrap();
        assert!(output.status.success());
        assert!(String::from_utf8_lossy(&output.stdout).contains("endless-setup"));
    }
    let output = f
        .command()
        .arg("tui")
        .arg("--sandbox")
        .arg(&f.sandbox)
        .arg("--manifest")
        .arg(&f.manifest)
        .output()
        .unwrap();
    assert!(output.status.success());
    assert_eq!(fs::read_dir(f.sandbox).unwrap().count(), 0);
}
#[test]
fn host_target_and_missing_sandbox_are_denied() {
    let f = Cli::new();
    let output = f
        .command()
        .args(["install", "--sandbox", "/etc", "--yes", "--json"])
        .arg("--manifest")
        .arg(&f.manifest)
        .output()
        .unwrap();
    assert!(!output.status.success());
    let output = f
        .command()
        .args(["install", "--yes", "--json"])
        .arg("--manifest")
        .arg(&f.manifest)
        .output()
        .unwrap();
    assert!(!output.status.success());
    assert_eq!(fs::read_dir(f.sandbox).unwrap().count(), 0);
}
