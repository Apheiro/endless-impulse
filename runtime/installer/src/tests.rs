use super::*;
use std::fs as disk;
use std::os::unix::fs::{PermissionsExt, symlink};
use tempfile::TempDir;

struct Fixture {
    _temp: TempDir,
    root: PathBuf,
    bundle: PathBuf,
    manifest: PathBuf,
}
impl Fixture {
    fn new(files: &[(&str, &str, Ownership)]) -> Self {
        // Deliberately ignore TMPDIR/HOME: every writer belongs to this fresh /tmp tree.
        let temp = tempfile::Builder::new()
            .prefix("endless-setup-test-")
            .tempdir_in("/tmp")
            .unwrap();
        let root = temp.path().join("sandbox");
        let bundle = temp.path().join("bundle");
        disk::create_dir(&root).unwrap();
        disk::create_dir(&bundle).unwrap();
        disk::set_permissions(&root, disk::Permissions::from_mode(0o700)).unwrap();
        let fixture = Self {
            manifest: bundle.join("manifest.json"),
            root,
            bundle,
            _temp: temp,
        };
        fixture.release("v1", files);
        fixture
    }
    fn release(&self, version: &str, files: &[(&str, &str, Ownership)]) {
        let mut rows = Vec::new();
        for (index, (target, content, ownership)) in files.iter().enumerate() {
            let source = format!("file-{index}");
            disk::write(self.bundle.join(&source), content).unwrap();
            rows.push(PayloadFile {
                source,
                destination: target.to_string(),
                sha256: digest(content.as_bytes()),
                category: Category::Data,
                ownership: *ownership,
                mode: 0o644,
            });
        }
        self.write_manifest(&Manifest {
            schema: 1,
            payload_version: version.into(),
            completeness: "subset".into(),
            dependencies: "not_implemented".into(),
            services: "not_implemented".into(),
            files: rows,
            assets: vec![],
        });
    }
    fn write_manifest(&self, manifest: &Manifest) {
        disk::write(&self.manifest, serde_json::to_vec(manifest).unwrap()).unwrap();
    }
    fn mutate_manifest(&self, change: impl FnOnce(&mut Manifest)) {
        let mut m: Manifest = serde_json::from_slice(&disk::read(&self.manifest).unwrap()).unwrap();
        change(&mut m);
        self.write_manifest(&m);
    }
    fn engine(&self) -> Engine {
        Engine::open(&self.root).unwrap()
    }
    fn plan(&self, action: Action) -> Plan {
        self.engine()
            .plan(action, Some(&self.manifest), false)
            .unwrap()
    }
    fn install(&self) {
        self.engine().execute(&self.plan(Action::Install)).unwrap();
    }
    fn put(&self, target: &str, value: &str) {
        relative(target).unwrap();
        let path = self.root.join(target);
        disk::create_dir_all(path.parent().unwrap()).unwrap();
        disk::write(path, value).unwrap();
        if target.starts_with(".endless-setup/") {
            disk::set_permissions(
                self.root.join(".endless-setup"),
                disk::Permissions::from_mode(0o700),
            )
            .unwrap();
        }
    }
    fn bytes(&self, target: &str) -> Vec<u8> {
        disk::read(self.root.join(target)).unwrap()
    }
    fn snapshot(&self) -> BTreeMap<PathBuf, Vec<u8>> {
        fn visit(path: &Path, root: &Path, out: &mut BTreeMap<PathBuf, Vec<u8>>) {
            for entry in disk::read_dir(path).unwrap() {
                let path = entry.unwrap().path();
                let meta = disk::symlink_metadata(&path).unwrap();
                assert!(!meta.file_type().is_symlink());
                if meta.is_dir() {
                    out.insert(path.strip_prefix(root).unwrap().to_path_buf(), vec![]);
                    visit(&path, root, out);
                } else {
                    out.insert(
                        path.strip_prefix(root).unwrap().to_path_buf(),
                        disk::read(&path).unwrap(),
                    );
                }
            }
        }
        let mut out = BTreeMap::new();
        visit(&self.root, &self.root, &mut out);
        out
    }
}
const MANAGED: Ownership = Ownership::Managed;

#[test]
fn clean_install_exact_inventory_and_permissions() {
    let f = Fixture::new(&[("icons/a", "one", MANAGED)]);
    f.install();
    assert_eq!(f.bytes("data/icons/a"), b"one");
    let (inventory, _) = f.engine().inventory().unwrap();
    assert_eq!(inventory.files.len(), 1);
    assert!(!f.root.join(JOURNAL).exists());
    assert_eq!(
        disk::metadata(f.root.join("data/icons/a")).unwrap().mode() & 0o777,
        0o644
    );
}
#[test]
fn preview_dry_plan_and_doctor_never_create_state() {
    let f = Fixture::new(&[("a", "one", MANAGED)]);
    let before = f.snapshot();
    assert!(f.plan(Action::Install).blocked.is_empty());
    doctor(Some(&f.manifest)).unwrap();
    assert_eq!(f.snapshot(), before);
    assert!(!f.root.join(".endless-setup").exists());
}
#[test]
fn collision_requires_opt_in_backs_up_and_uninstall_restores_mode() {
    let f = Fixture::new(&[("a", "payload", MANAGED)]);
    f.put("data/a", "original");
    disk::set_permissions(f.root.join("data/a"), disk::Permissions::from_mode(0o600)).unwrap();
    let plan = f.plan(Action::Install);
    assert!(!plan.blocked.is_empty());
    assert!(f.engine().execute(&plan).is_err());
    let plan = f
        .engine()
        .plan(Action::Install, Some(&f.manifest), true)
        .unwrap();
    f.engine().execute(&plan).unwrap();
    assert_eq!(
        f.bytes(&format!(".endless-setup/backups/{}", digest(b"original"))),
        b"original"
    );
    f.engine().execute(&f.plan(Action::Uninstall)).unwrap();
    assert_eq!(f.bytes("data/a"), b"original");
    assert_eq!(
        disk::metadata(f.root.join("data/a")).unwrap().mode() & 0o777,
        0o600
    );
    assert!(
        f.root
            .join(format!(".endless-setup/backups/{}", digest(b"original")))
            .exists()
    );
}
#[test]
fn install_twice_is_byte_identical() {
    let f = Fixture::new(&[("a", "one", MANAGED)]);
    f.install();
    let before = f.snapshot();
    let report = f.engine().execute(&f.plan(Action::Install)).unwrap();
    assert_eq!(report.status, "unchanged");
    assert_eq!(f.snapshot(), before);
}
#[test]
fn update_handles_renamed_deleted_files_and_unrelated_siblings() {
    let f = Fixture::new(&[("a", "old", MANAGED), ("obsolete", "delete", MANAGED)]);
    f.install();
    f.put("data/third-party", "stay");
    f.release("v2", &[("renamed", "new", MANAGED)]);
    f.engine().execute(&f.plan(Action::Update)).unwrap();
    assert!(!f.root.join("data/a").exists());
    assert!(!f.root.join("data/obsolete").exists());
    assert_eq!(f.bytes("data/renamed"), b"new");
    assert_eq!(f.bytes("data/third-party"), b"stay");
}
#[test]
fn update_removed_file_restores_recorded_original() {
    let f = Fixture::new(&[("a", "managed", MANAGED)]);
    f.put("data/a", "original");
    f.engine()
        .execute(
            &f.engine()
                .plan(Action::Install, Some(&f.manifest), true)
                .unwrap(),
        )
        .unwrap();
    f.release("v2", &[("b", "new", MANAGED)]);
    f.engine().execute(&f.plan(Action::Update)).unwrap();
    assert_eq!(f.bytes("data/a"), b"original");
}
#[test]
fn modified_files_block_update_but_uninstall_preserves_with_residual_inventory() {
    let f = Fixture::new(&[("a", "one", MANAGED), ("b", "two", MANAGED)]);
    f.install();
    f.put("data/a", "personal edit");
    f.put("data/unrelated", "third party");
    f.release("v2", &[("a", "new", MANAGED)]);
    assert!(!f.plan(Action::Update).blocked.is_empty());
    f.engine().execute(&f.plan(Action::Uninstall)).unwrap();
    assert_eq!(f.bytes("data/a"), b"personal edit");
    assert_eq!(f.bytes("data/unrelated"), b"third party");
    assert!(!f.root.join("data/b").exists());
    assert!(f.root.join("data").is_dir());
    assert!(
        f.engine()
            .inventory()
            .unwrap()
            .0
            .files
            .contains_key("data/a")
    );
}
#[test]
fn removed_but_modified_file_survives_release_update() {
    let f = Fixture::new(&[("a", "one", MANAGED)]);
    f.install();
    f.put("data/a", "changed");
    f.release("v2", &[("b", "two", MANAGED)]);
    let plan = f.plan(Action::Update);
    assert!(plan.blocked.is_empty());
    f.engine().execute(&plan).unwrap();
    assert_eq!(f.bytes("data/a"), b"changed");
}
#[test]
fn repair_recreates_missing_managed_and_refuses_modified() {
    let f = Fixture::new(&[("a", "one", MANAGED)]);
    f.install();
    disk::remove_file(f.root.join("data/a")).unwrap();
    f.engine().execute(&f.plan(Action::Repair)).unwrap();
    assert_eq!(f.bytes("data/a"), b"one");
    f.put("data/a", "edit");
    assert!(!f.plan(Action::Repair).blocked.is_empty());
}
#[test]
fn user_seed_and_preexisting_custom_remain_personal() {
    let f = Fixture::new(&[
        ("custom", "seed", Ownership::User),
        ("existing", "seed", Ownership::User),
    ]);
    f.put("data/existing", "personal");
    f.install();
    f.put("data/custom", "edited");
    f.release("v2", &[("custom", "new seed", Ownership::User)]);
    f.engine().execute(&f.plan(Action::Update)).unwrap();
    f.engine().execute(&f.plan(Action::Uninstall)).unwrap();
    assert_eq!(f.bytes("data/custom"), b"edited");
    assert_eq!(f.bytes("data/existing"), b"personal");
}
#[test]
fn unsafe_sources_destinations_and_overlaps_are_rejected() {
    for bad in [
        "../escape",
        "/absolute",
        "a/../b",
        "./a",
        "a//b",
        "a\\b",
        "a\n",
        "",
    ] {
        let f = Fixture::new(&[("a", "one", MANAGED)]);
        f.mutate_manifest(|m| m.files[0].destination = bad.into());
        assert!(
            f.engine()
                .plan(Action::Install, Some(&f.manifest), false)
                .is_err()
        );
        f.release("v1", &[("a", "one", MANAGED)]);
        f.mutate_manifest(|m| m.files[0].source = bad.into());
        assert!(
            f.engine()
                .plan(Action::Install, Some(&f.manifest), false)
                .is_err()
        );
        assert!(f.snapshot().is_empty());
    }
    for names in [["a", "a"], ["a", "a/b"], ["a/b", "a"]] {
        let f = Fixture::new(&[(names[0], "one", MANAGED), (names[1], "two", MANAGED)]);
        assert!(
            f.engine()
                .plan(Action::Install, Some(&f.manifest), false)
                .is_err()
        );
    }
    assert!(no_overlaps(["data/a".into(), "data/a-b".into(), "data/a/c".into()].iter()).is_err());
}
#[test]
fn payload_missing_wrong_hash_unknown_schema_and_complete_mode_fail_closed() {
    let f = Fixture::new(&[("a", "one", MANAGED)]);
    disk::remove_file(f.bundle.join("file-0")).unwrap();
    assert!(
        f.engine()
            .plan(Action::Install, Some(&f.manifest), false)
            .is_err()
    );
    f.release("v1", &[("a", "one", MANAGED)]);
    disk::write(f.bundle.join("file-0"), "tampered").unwrap();
    assert!(
        f.engine()
            .plan(Action::Install, Some(&f.manifest), false)
            .is_err()
    );
    f.release("v1", &[("a", "one", MANAGED)]);
    f.mutate_manifest(|m| m.schema = 2);
    assert!(
        f.engine()
            .plan(Action::Install, Some(&f.manifest), false)
            .is_err()
    );
    f.mutate_manifest(|m| {
        m.schema = 1;
        m.completeness = "complete".into();
    });
    assert!(
        f.engine()
            .plan(Action::Install, Some(&f.manifest), false)
            .is_err()
    );
    assert!(f.snapshot().is_empty());
}
#[test]
fn symlink_sources_parent_leaf_root_and_hardlinks_are_rejected() {
    let f = Fixture::new(&[("a", "one", MANAGED)]);
    let outside = f._temp.path().join("outside");
    disk::create_dir(&outside).unwrap();
    disk::write(outside.join("a"), "sentinel").unwrap();
    symlink(&outside, f.root.join("data")).unwrap();
    assert!(!f.plan(Action::Install).blocked.is_empty());
    assert_eq!(disk::read(outside.join("a")).unwrap(), b"sentinel");
    disk::remove_file(f.root.join("data")).unwrap();
    disk::create_dir(f.root.join("data")).unwrap();
    symlink(outside.join("a"), f.root.join("data/a")).unwrap();
    assert!(!f.plan(Action::Install).blocked.is_empty());
    disk::remove_file(f.root.join("data/a")).unwrap();
    disk::hard_link(outside.join("a"), f.root.join("data/a")).unwrap();
    assert!(!f.plan(Action::Install).blocked.is_empty());
    disk::remove_file(f.root.join("data/a")).unwrap();
    disk::remove_file(f.bundle.join("file-0")).unwrap();
    symlink(outside.join("a"), f.bundle.join("file-0")).unwrap();
    assert!(
        f.engine()
            .plan(Action::Install, Some(&f.manifest), false)
            .is_err()
    );
    let alias = f._temp.path().join("alias");
    symlink(&f.root, &alias).unwrap();
    assert!(Engine::open(&alias).is_err());
    assert!(Engine::open(Path::new("/tmp")).is_err());
    assert!(Engine::open(Path::new("/")).is_err());
}
#[test]
fn changes_after_preview_and_parent_swaps_are_rejected_without_escape() {
    let f = Fixture::new(&[("a", "one", MANAGED)]);
    let plan = f.plan(Action::Install);
    f.put("data/a", "late");
    assert!(f.engine().execute(&plan).is_err());
    assert_eq!(f.bytes("data/a"), b"late");
    let f = Fixture::new(&[("a", "one", MANAGED)]);
    let plan = f.plan(Action::Install);
    let outside = f._temp.path().join("outside");
    disk::create_dir(&outside).unwrap();
    symlink(&outside, f.root.join("data")).unwrap();
    assert!(f.engine().execute(&plan).is_err());
    assert!(!outside.join("a").exists());
}
#[test]
fn corrupt_state_and_journal_refuse_all_deployment() {
    let f = Fixture::new(&[("a", "one", MANAGED)]);
    f.put(INVENTORY, "not json");
    assert!(
        f.engine()
            .plan(Action::Install, Some(&f.manifest), false)
            .is_err()
    );
    disk::remove_file(f.root.join(INVENTORY)).unwrap();
    f.put(JOURNAL, "broken");
    assert!(!f.plan(Action::Install).blocked.is_empty());
    assert!(f.engine().recover().is_err());
    assert_eq!(f.bytes(JOURNAL), b"broken");
}
#[test]
fn injected_failure_rolls_back_clean_and_preexisting_install() {
    for preexisting in [false, true] {
        let f = Fixture::new(&[("a", "one", MANAGED), ("b", "two", MANAGED)]);
        if preexisting {
            f.put("data/a", "original");
        }
        let plan = f
            .engine()
            .plan(Action::Install, Some(&f.manifest), true)
            .unwrap();
        assert!(
            f.engine()
                .execute_inner(&plan, Fault::FailAfter(2))
                .is_err()
        );
        assert!(!f.root.join(JOURNAL).exists());
        assert!(!f.root.join(INVENTORY).exists());
        if preexisting {
            assert_eq!(f.bytes("data/a"), b"original");
        } else {
            assert!(!f.root.join("data/a").exists());
        }
        assert!(!f.root.join("data/b").exists());
    }
}
#[test]
fn interrupted_transaction_is_recovered_by_new_engine_even_after_commit() {
    for index in [1, 2, 3] {
        let f = Fixture::new(&[("a", "one", MANAGED), ("b", "two", MANAGED)]);
        assert!(
            f.engine()
                .execute_inner(&f.plan(Action::Install), Fault::InterruptAfter(index))
                .is_err()
        );
        assert!(f.root.join(JOURNAL).exists());
        let before = f.snapshot();
        assert!(!f.plan(Action::Install).blocked.is_empty());
        assert_eq!(f.snapshot(), before);
        f.engine().recover().unwrap();
        f.engine().recover().unwrap();
        assert!(!f.root.join("data/a").exists());
        assert!(!f.root.join("data/b").exists());
        assert!(!f.root.join(INVENTORY).exists());
        f.install();
        assert_eq!(f.bytes("data/a"), b"one");
    }
}
#[test]
fn recovery_retains_journal_and_original_when_external_change_blocks_it() {
    let f = Fixture::new(&[("a", "one", MANAGED)]);
    assert!(
        f.engine()
            .execute_inner(&f.plan(Action::Install), Fault::InterruptAfter(1))
            .is_err()
    );
    f.put("data/a", "external");
    assert!(f.engine().recover().is_err());
    assert_eq!(f.bytes("data/a"), b"external");
    assert!(f.root.join(JOURNAL).exists());
    f.put("data/a", "one");
    disk::set_permissions(f.root.join("data/a"), disk::Permissions::from_mode(0o644)).unwrap();
    f.engine().recover().unwrap();
    assert!(!f.root.join("data/a").exists());
}
#[test]
fn lock_is_nonblocking_and_never_unlinks_another_lock() {
    let f = Fixture::new(&[("a", "one", MANAGED)]);
    let engine = f.engine();
    let lock = engine.dir.lock().unwrap();
    assert!(f.engine().execute(&f.plan(Action::Install)).is_err());
    assert!(f.root.join(".endless-setup/lock").exists());
    drop(lock);
    f.install();
}
#[test]
fn non_utf8_unrelated_file_is_preserved() {
    use std::ffi::OsStr;
    use std::os::unix::ffi::OsStrExt;
    let f = Fixture::new(&[("a", "one", MANAGED)]);
    let odd = f.root.join(OsStr::from_bytes(b"personal-\xff"));
    disk::write(&odd, "private").unwrap();
    f.install();
    f.engine().execute(&f.plan(Action::Uninstall)).unwrap();
    assert_eq!(disk::read(odd).unwrap(), b"private");
}
#[test]
fn original_backup_corruption_blocks_restore() {
    let f = Fixture::new(&[("a", "one", MANAGED)]);
    f.put("data/a", "original");
    f.engine()
        .execute(
            &f.engine()
                .plan(Action::Install, Some(&f.manifest), true)
                .unwrap(),
        )
        .unwrap();
    f.put(
        &format!(".endless-setup/backups/{}", digest(b"original")),
        "corrupt",
    );
    assert!(f.engine().plan(Action::Uninstall, None, false).is_err());
    assert_eq!(f.bytes("data/a"), b"one");
}

#[test]
fn plans_are_sealed_and_existing_backups_rechecked() {
    let f = Fixture::new(&[("a", "one", MANAGED)]);
    let mut plan = f.plan(Action::Install);
    plan.operations.clear();
    assert!(f.engine().execute(&plan).is_err());
    assert!(f.snapshot().is_empty());
    f.put("data/a", "original");
    let mut blocked = f.plan(Action::Install);
    blocked.blocked.clear();
    assert!(f.engine().execute(&blocked).is_err());
    let backup = format!(".endless-setup/backups/{}", digest(b"original"));
    f.put(&backup, "original");
    let plan = f
        .engine()
        .plan(Action::Install, Some(&f.manifest), true)
        .unwrap();
    f.put(&backup, "changed after preview");
    assert!(f.engine().execute(&plan).is_err());
    assert_eq!(f.bytes("data/a"), b"original");
}

#[test]
fn malformed_inventory_paths_and_unknown_fields_are_rejected() {
    let f = Fixture::new(&[("a", "one", MANAGED)]);
    f.install();
    let mut raw: serde_json::Value = serde_json::from_slice(&f.bytes(INVENTORY)).unwrap();
    let entry = raw["files"]["data/a"].take();
    raw["files"] = serde_json::json!({"../../outside": entry});
    disk::write(f.root.join(INVENTORY), serde_json::to_vec(&raw).unwrap()).unwrap();
    assert!(f.engine().plan(Action::Uninstall, None, false).is_err());
    assert_eq!(f.bytes("data/a"), b"one");
    f.release("v1", &[("a", "one", MANAGED)]);
    let mut manifest: serde_json::Value =
        serde_json::from_slice(&disk::read(&f.manifest).unwrap()).unwrap();
    manifest["command"] = "anything".into();
    disk::write(&f.manifest, serde_json::to_vec(&manifest).unwrap()).unwrap();
    assert!(doctor(Some(&f.manifest)).is_err());
}

#[test]
fn doctor_inventory_is_read_only_and_reports_missing_modified_and_pending() {
    let f = Fixture::new(&[("a", "one", MANAGED), ("b", "two", MANAGED)]);
    f.install();
    disk::remove_file(f.root.join("data/a")).unwrap();
    f.put("data/b", "changed");
    let before = f.snapshot();
    let inspect = f.engine().inspect().unwrap();
    assert_eq!(inspect.files[0].status, "missing");
    assert_eq!(inspect.files[1].status, "modified_preserve");
    assert_eq!(f.snapshot(), before);
}

#[test]
fn arbitrary_original_permissions_are_restored_and_source_links_refused() {
    let f = Fixture::new(&[("a", "one", MANAGED)]);
    f.put("data/a", "personal");
    disk::set_permissions(f.root.join("data/a"), disk::Permissions::from_mode(0o640)).unwrap();
    f.engine()
        .execute(
            &f.engine()
                .plan(Action::Install, Some(&f.manifest), true)
                .unwrap(),
        )
        .unwrap();
    f.engine().execute(&f.plan(Action::Uninstall)).unwrap();
    assert_eq!(
        disk::metadata(f.root.join("data/a")).unwrap().mode() & 0o777,
        0o640
    );
    disk::hard_link(f.bundle.join("file-0"), f.bundle.join("alias")).unwrap();
    assert!(doctor(Some(&f.manifest)).is_err());
}

#[test]
fn dangling_symlink_and_state_symlink_fail_closed() {
    let f = Fixture::new(&[("a", "one", MANAGED)]);
    let missing = f._temp.path().join("missing");
    disk::create_dir(f.root.join("data")).unwrap();
    symlink(&missing, f.root.join("data/a")).unwrap();
    assert!(!f.plan(Action::Install).blocked.is_empty());
    assert!(!missing.exists());
    disk::remove_file(f.root.join("data/a")).unwrap();
    let outside = f._temp.path().join("outside");
    disk::create_dir(&outside).unwrap();
    symlink(&outside, f.root.join(".endless-setup")).unwrap();
    assert!(
        f.engine()
            .plan(Action::Install, Some(&f.manifest), false)
            .is_err()
    );
    assert!(f.engine().recover().is_err());
    assert_eq!(disk::read_dir(outside).unwrap().count(), 0);
}

#[test]
fn interrupted_update_restores_previous_inventory_and_payload() {
    let f = Fixture::new(&[("a", "one", MANAGED)]);
    f.install();
    let inventory = f.bytes(INVENTORY);
    f.release("v2", &[("b", "two", MANAGED)]);
    assert!(
        f.engine()
            .execute_inner(&f.plan(Action::Update), Fault::InterruptAfter(2))
            .is_err()
    );
    f.engine().recover().unwrap();
    assert_eq!(f.bytes("data/a"), b"one");
    assert!(!f.root.join("data/b").exists());
    assert_eq!(f.bytes(INVENTORY), inventory);
}

// Worker is a test-only subprocess: exit(87) occurs with the execution lock held.
// No failure injection exists in the release CLI or through production env vars.
#[test]
fn crash_worker() {
    let Some(root) = std::env::var_os("ENDLESS_TEST_SANDBOX") else {
        return;
    };
    let manifest = PathBuf::from(std::env::var_os("ENDLESS_TEST_MANIFEST").unwrap());
    let engine = Engine::open(Path::new(&root)).unwrap();
    let plan = engine
        .plan(Action::Install, Some(&manifest), false)
        .unwrap();
    engine.execute_inner(&plan, Fault::ExitAfter(1)).unwrap();
    panic!("Worker should have exited inside the transaction");
}
#[test]
fn actual_process_exit_leaves_recoverable_durable_journal() {
    let f = Fixture::new(&[("a", "one", MANAGED), ("b", "two", MANAGED)]);
    let status = std::process::Command::new(std::env::current_exe().unwrap())
        .args(["--exact", "tests::crash_worker", "--nocapture"])
        .env("ENDLESS_TEST_SANDBOX", &f.root)
        .env("ENDLESS_TEST_MANIFEST", &f.manifest)
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .unwrap();
    assert_eq!(status.code(), Some(87));
    assert!(f.root.join(JOURNAL).exists());
    f.engine().recover().unwrap();
    assert!(!f.root.join("data/a").exists());
    f.install();
}

#[test]
fn confined_io_rejects_nested_mounts_without_creating_any_mount() {
    // /proc is already a distinct kernel mount. This is a read-only syscall
    // probe; the test neither mounts anything nor creates files outside /tmp.
    if Path::new("/proc/version").exists() {
        let root = Dir::absolute(Path::new("/")).unwrap().confined().unwrap();
        assert!(root.read("proc/version").is_err());
    }
}

#[test]
fn missing_reference_asset_and_wrong_digest_fail_before_writing() {
    let f = Fixture::new(&[("a", "one", MANAGED)]);
    f.mutate_manifest(|m| {
        m.assets.push(Asset {
            source: "missing-reference".into(),
            sha256: digest(b"reference"),
            role: AssetRole::ArchDependencies,
        })
    });
    assert!(doctor(Some(&f.manifest)).is_err());
    disk::write(f.bundle.join("missing-reference"), "wrong bytes").unwrap();
    assert!(
        f.engine()
            .plan(Action::Install, Some(&f.manifest), false)
            .is_err()
    );
    assert!(f.snapshot().is_empty());
}

#[test]
fn unsafe_state_permissions_and_foreign_lock_fail_closed() {
    let f = Fixture::new(&[("a", "one", MANAGED)]);
    f.put(".endless-setup/lock", "not an engine lock");
    assert!(
        f.engine()
            .plan(Action::Install, Some(&f.manifest), false)
            .is_err()
    );
    assert_eq!(f.bytes(".endless-setup/lock"), b"not an engine lock");
    disk::set_permissions(
        f.root.join(".endless-setup"),
        disk::Permissions::from_mode(0o755),
    )
    .unwrap();
    assert!(f.engine().inspect().is_err());
    assert!(f.engine().recover().is_err());
    disk::set_permissions(&f.root, disk::Permissions::from_mode(0o755)).unwrap();
    assert!(Engine::open(&f.root).is_err());
}
