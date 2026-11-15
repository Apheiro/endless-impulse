//! Experimental deployment core. No host installation, shell commands or service actions.
mod fs;
use fs::{Dir, Image, MAX_FILE};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::os::unix::fs::MetadataExt;
use std::path::{Path, PathBuf};

const INVENTORY: &str = ".endless-setup/inventory.json";
const JOURNAL: &str = ".endless-setup/journal.json";
const WARNING: &str =
    "EXPERIMENTAL SANDBOX ONLY — representative subset, not a desktop installation";
pub type Result<T> = std::result::Result<T, Error>;
#[derive(Debug)]
pub enum Error {
    Io(std::io::Error),
    Json(serde_json::Error),
    Invalid(String),
}
impl Error {
    pub(crate) fn msg(value: impl Into<String>) -> Self {
        Self::Invalid(value.into())
    }
}
impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Io(e) => write!(f, "{e}"),
            Self::Json(e) => write!(f, "Invalid JSON: {e}"),
            Self::Invalid(e) => write!(f, "{e}"),
        }
    }
}
impl std::error::Error for Error {}
impl From<std::io::Error> for Error {
    fn from(e: std::io::Error) -> Self {
        Self::Io(e)
    }
}
impl From<serde_json::Error> for Error {
    fn from(e: serde_json::Error) -> Self {
        Self::Json(e)
    }
}
pub fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn relative(value: &str) -> Result<()> {
    if value.is_empty()
        || value.contains('\\')
        || value.chars().any(char::is_control)
        || value.split('/').any(|part| {
            part.is_empty()
                || part == "."
                || part == ".."
                || part.starts_with(".endless-setup-tmp-")
        })
    {
        return Err(Error::msg(format!("Unsafe relative path: {value:?}")));
    }
    Ok(())
}
fn valid_hash(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
}
fn valid_mode(mode: u32) -> bool {
    matches!(mode, 0o600 | 0o644 | 0o700 | 0o755)
}
fn default_mode() -> u32 {
    0o644
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Category {
    QuickshellConfig,
    HyprConfig,
    Data,
    Runtime,
}
impl Category {
    fn base(self) -> &'static str {
        match self {
            Self::QuickshellConfig => "config/quickshell/endless-Impulse",
            Self::HyprConfig => "config/hypr",
            Self::Data => "data",
            Self::Runtime => "runtime/endless-Impulse",
        }
    }
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Ownership {
    Managed,
    User,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PayloadFile {
    pub source: String,
    pub category: Category,
    pub destination: String,
    pub sha256: String,
    pub ownership: Ownership,
    #[serde(default = "default_mode")]
    pub mode: u32,
}
impl PayloadFile {
    fn target(&self) -> Result<String> {
        relative(&self.source)?;
        relative(&self.destination)?;
        if !valid_hash(&self.sha256) || !valid_mode(self.mode) {
            return Err(Error::msg("Invalid digest or file mode"));
        }
        Ok(format!("{}/{}", self.category.base(), self.destination))
    }
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Manifest {
    pub schema: u32,
    pub payload_version: String,
    pub completeness: String,
    pub dependencies: String,
    pub services: String,
    pub files: Vec<PayloadFile>,
    #[serde(default)]
    pub assets: Vec<Asset>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Asset {
    pub source: String,
    pub sha256: String,
    pub role: AssetRole,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AssetRole {
    ArchDependencies,
    ServicesReference,
    License,
}
fn load_manifest(path: &Path) -> Result<(Manifest, BTreeMap<String, Image>)> {
    let path = std::path::absolute(path)?;
    let parent = Dir::absolute(
        path.parent()
            .ok_or_else(|| Error::msg("Manifest parent missing"))?,
    )?
    .confined()?;
    let name = path
        .file_name()
        .and_then(|s| s.to_str())
        .ok_or_else(|| Error::msg("Manifest filename must be UTF-8"))?;
    let raw = parent
        .read(name)?
        .ok_or_else(|| Error::msg("Missing manifest"))?;
    let manifest: Manifest = serde_json::from_slice(&raw.bytes)?;
    if manifest.schema != 1
        || manifest.payload_version.is_empty()
        || manifest.payload_version.len() > 128
        || manifest.payload_version.chars().any(char::is_control)
        || manifest.completeness != "subset"
        || manifest.dependencies != "not_implemented"
        || manifest.services != "not_implemented"
    {
        return Err(Error::msg(
            "Only schema 1, subset payloads and not_implemented integrations are accepted",
        ));
    }
    if manifest.files.is_empty() || manifest.files.len() > 512 {
        return Err(Error::msg("Payload must contain 1..512 exact files"));
    }
    if manifest.assets.len() > 16 {
        return Err(Error::msg("Too many reference assets"));
    }
    let mut asset_sources = BTreeSet::new();
    for asset in &manifest.assets {
        relative(&asset.source)?;
        if !valid_hash(&asset.sha256) || !asset_sources.insert(&asset.source) {
            return Err(Error::msg("Invalid/duplicate reference asset"));
        }
        let image = parent
            .read(&asset.source)?
            .ok_or_else(|| Error::msg("Missing reference asset"))?;
        if image.sha() != asset.sha256 {
            return Err(Error::msg(format!(
                "Reference asset digest mismatch: {}",
                asset.source
            )));
        }
    }
    let mut payload = BTreeMap::new();
    let mut size = 0;
    for file in &manifest.files {
        let target = file.target()?;
        if payload.contains_key(&target) {
            return Err(Error::msg(format!("Duplicate target: {target}")));
        }
        let mut image = parent
            .read(&file.source)?
            .ok_or_else(|| Error::msg(format!("Missing payload: {}", file.source)))?;
        if image.sha() != file.sha256 {
            return Err(Error::msg(format!("SHA-256 mismatch: {}", file.source)));
        }
        size += image.bytes.len();
        if size > 8 * MAX_FILE {
            return Err(Error::msg("Subset exceeds 32 MiB"));
        }
        image.mode = file.mode;
        payload.insert(target, image);
    }
    no_overlaps(payload.keys())?;
    Ok((manifest, payload))
}
fn no_overlaps<'a>(paths: impl Iterator<Item = &'a String>) -> Result<()> {
    let paths: BTreeSet<_> = paths.collect();
    for path in &paths {
        for (index, _) in path.match_indices('/') {
            if paths.iter().any(|p| p.as_str() == &path[..index]) {
                return Err(Error::msg(format!("Overlapping file paths: {path}")));
            }
        }
    }
    Ok(())
}
fn controlled(path: &str) -> Result<()> {
    relative(path)?;
    if [
        Category::QuickshellConfig,
        Category::HyprConfig,
        Category::Data,
        Category::Runtime,
    ]
    .iter()
    .any(|c| path.starts_with(&format!("{}/", c.base())))
    {
        Ok(())
    } else {
        Err(Error::msg(format!("Uncontrolled target: {path}")))
    }
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Original {
    sha256: String,
    mode: u32,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Entry {
    sha256: String,
    mode: u32,
    ownership: Ownership,
    original: Option<Original>,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Inventory {
    schema: u32,
    payload_version: String,
    files: BTreeMap<String, Entry>,
}
impl Inventory {
    fn empty() -> Self {
        Self {
            schema: 1,
            payload_version: String::new(),
            files: BTreeMap::new(),
        }
    }
    fn validate(&self) -> Result<()> {
        if self.schema != 1 || self.files.len() > 1024 {
            return Err(Error::msg("Unsupported/corrupt inventory"));
        }
        for (path, entry) in &self.files {
            controlled(path)?;
            if !valid_hash(&entry.sha256)
                || !valid_mode(entry.mode)
                || entry
                    .original
                    .as_ref()
                    .is_some_and(|v| !valid_hash(&v.sha256) || v.mode > 0o777)
            {
                return Err(Error::msg("Corrupt inventory entry"));
            }
        }
        no_overlaps(self.files.keys())
    }
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Action {
    Install,
    Update,
    Repair,
    Uninstall,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct Operation {
    pub path: String,
    pub absolute_path: PathBuf,
    pub kind: String,
    pub reason: String,
    pub before_sha256: Option<String>,
    pub after_sha256: Option<String>,
    pub before_mode: Option<u32>,
    pub after_mode: Option<u32>,
}
#[derive(Clone, Debug, Serialize)]
pub struct Plan {
    pub action: Action,
    pub sandbox: PathBuf,
    pub payload_version: String,
    pub completeness: String,
    pub blocked: Vec<String>,
    pub warnings: Vec<String>,
    pub operations: Vec<Operation>,
    pub state_effects: Vec<Operation>,
    pub backups: Vec<String>,
    #[serde(skip)]
    prepared: Prepared,
}
#[derive(Clone, Debug, PartialEq, Eq, Default)]
struct Prepared {
    executable: bool,
    seal: String,
    inventory_before: Option<Image>,
    inventory_after: Option<Image>,
    changes: Vec<Change>,
    observed: BTreeMap<String, Option<Image>>,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Change {
    path: String,
    before: Option<Image>,
    after: Option<Image>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Journal {
    schema: u32,
    inventory_before: Option<Image>,
    inventory_after: Image,
    changes: Vec<Change>,
}
#[derive(Debug, Serialize)]
pub struct Report {
    pub status: String,
    pub message: String,
    pub operations: usize,
}
pub struct Engine {
    root: PathBuf,
    dir: Dir,
}
impl Engine {
    pub fn open(sandbox: &Path) -> Result<Self> {
        if !sandbox.is_absolute() {
            return Err(Error::msg(
                "--sandbox must be an existing absolute private directory under /tmp",
            ));
        }
        let canonical = sandbox.canonicalize()?;
        if canonical != sandbox || !canonical.starts_with("/tmp") || canonical == Path::new("/tmp")
        {
            return Err(Error::msg(
                "Only canonical, symlink-free sandbox directories below /tmp are supported; real host targets are disabled",
            ));
        }
        if let Some(home) = std::env::var_os("HOME")
            && let Ok(home) = PathBuf::from(home).canonicalize()
            && canonical.starts_with(home)
        {
            return Err(Error::msg("HOME and its descendants are forbidden"));
        }
        // Anchor at /tmp BEFORE walking the requested root, rejecting a bind
        // mount used as the sandbox itself as well as mounts inside it.
        let dir = Dir::absolute(Path::new("/tmp"))?.confined()?.below(
            canonical
                .strip_prefix("/tmp")
                .map_err(|_| Error::msg("Invalid sandbox prefix"))?,
        )?;
        let metadata = dir.metadata()?;
        // SAFETY: geteuid takes no arguments.
        if metadata.uid() != unsafe { libc::geteuid() } || metadata.mode() & 0o7777 != 0o700 {
            return Err(Error::msg(
                "Sandbox must be owned by this user with permissions 0700",
            ));
        }
        Ok(Self {
            root: canonical,
            dir,
        })
    }
    fn inventory(&self) -> Result<(Inventory, Option<Image>)> {
        self.dir.check_state()?;
        let raw = self.dir.read(INVENTORY)?;
        let inventory: Inventory = raw
            .as_ref()
            .map(|v| serde_json::from_slice(&v.bytes))
            .transpose()?
            .unwrap_or_else(Inventory::empty);
        inventory.validate()?;
        Ok((inventory, raw))
    }
    fn original(&self, original: &Original) -> Result<Image> {
        let path = format!(".endless-setup/backups/{}", original.sha256);
        let mut image = self
            .dir
            .read(&path)?
            .ok_or_else(|| Error::msg(format!("Original backup missing: {path}")))?;
        if image.sha() != original.sha256 {
            return Err(Error::msg("Original backup digest mismatch"));
        }
        image.mode = original.mode;
        Ok(image)
    }
    pub fn plan(
        &self,
        action: Action,
        manifest: Option<&Path>,
        allow_replace: bool,
    ) -> Result<Plan> {
        let (previous, raw) = self.inventory()?;
        let mut plan = Plan {
            action,
            sandbox: self.root.clone(),
            payload_version: previous.payload_version.clone(),
            completeness: "subset".into(),
            blocked: vec![],
            warnings: vec![WARNING.into()],
            operations: vec![],
            state_effects: vec![],
            backups: vec![],
            prepared: Prepared {
                inventory_before: raw.clone(),
                ..Prepared::default()
            },
        };
        if self.dir.read(JOURNAL)?.is_some() {
            plan.blocked.push(
                "Pending transaction: run recover explicitly before planning mutations".into(),
            );
            return Ok(plan);
        }
        let (manifest, payload) = if action == Action::Uninstall {
            (None, BTreeMap::new())
        } else {
            let (m, p) =
                load_manifest(manifest.ok_or_else(|| Error::msg("--manifest is required"))?)?;
            plan.payload_version = m.payload_version.clone();
            (Some(m), p)
        };
        if let Some(m) = &manifest
            && !previous.files.is_empty()
            && matches!(action, Action::Install | Action::Repair)
            && m.payload_version != previous.payload_version
        {
            plan.blocked.push("Install/repair requires the recorded payload version; use update for a different release".into());
        }
        let mut next = previous.clone();
        next.payload_version = plan.payload_version.clone();
        let wanted: BTreeMap<String, &PayloadFile> = manifest
            .as_ref()
            .map(|m| {
                m.files
                    .iter()
                    .map(|f| Ok((f.target()?, f)))
                    .collect::<Result<_>>()
            })
            .transpose()?
            .unwrap_or_default();
        let all: BTreeSet<_> = previous
            .files
            .keys()
            .chain(payload.keys())
            .cloned()
            .collect();
        no_overlaps(all.iter())?;
        for path in all {
            let current = match self.dir.read(&path) {
                Ok(v) => v,
                Err(error) => {
                    plan.blocked.push(format!("{path}: {error}"));
                    continue;
                }
            };
            plan.prepared.observed.insert(path.clone(), current.clone());
            let old = previous.files.get(&path);
            if let Some(original) = old.and_then(|e| e.original.as_ref()) {
                self.original(original)?;
                let backup = format!(".endless-setup/backups/{}", original.sha256);
                plan.prepared
                    .observed
                    .insert(backup.clone(), self.dir.read(&backup)?);
            }
            let desired = payload.get(&path);
            let kind;
            let reason;
            if let Some(old) = old {
                if old.ownership == Ownership::User {
                    kind = "preserve";
                    reason = "User-owned seed is never updated, repaired or removed";
                    if desired.is_none() {
                        next.files.remove(&path);
                    }
                } else if current
                    .as_ref()
                    .is_some_and(|image| image.sha() != old.sha256 || image.mode != old.mode)
                {
                    if desired.is_some() {
                        plan.blocked.push(format!("Locally modified managed file: {path}; back up manually or omit it from the payload"));
                    }
                    kind = "preserve";
                    reason = "Locally modified; retained in residual inventory";
                    plan.warnings
                        .push(format!("Preserved modified file: {path}"));
                } else if let Some(desired) = desired {
                    let file = wanted[&path];
                    if file.ownership != old.ownership {
                        plan.blocked.push(format!(
                            "Ownership transition requires manual review: {path}"
                        ));
                    }
                    kind = if current.as_ref() == Some(desired) {
                        "unchanged"
                    } else if current.is_none() {
                        "create"
                    } else {
                        "replace"
                    };
                    reason = "Managed payload file";
                    plan.change(&path, current.clone(), Some(desired.clone()));
                    next.files.insert(
                        path.clone(),
                        Entry {
                            sha256: desired.sha(),
                            mode: desired.mode,
                            ownership: file.ownership,
                            original: old.original.clone(),
                        },
                    );
                } else if current.is_none() {
                    kind = "preserve";
                    reason = "Managed file is already missing; original backup retained";
                    next.files.remove(&path);
                } else {
                    let original = old
                        .original
                        .as_ref()
                        .map(|v| self.original(v))
                        .transpose()?;
                    kind = if original.is_some() {
                        "restore"
                    } else {
                        "remove"
                    };
                    reason = "Intact managed file removed by release or uninstall";
                    plan.change(&path, current.clone(), original);
                    next.files.remove(&path);
                }
            } else if let Some(desired) = desired {
                let file = wanted[&path];
                if current.is_some() && file.ownership == Ownership::User {
                    kind = "preserve";
                    reason = "Preexisting user file stays outside inventory";
                } else if current.is_some() && !allow_replace {
                    plan.blocked.push(format!("Unowned collision: {path}; --allow-replace explicitly permits backup and replacement"));
                    kind = "blocked";
                    reason = "Outside installer ownership";
                } else {
                    let original = if let Some(image) = &current {
                        let sha = image.sha();
                        let backup = format!(".endless-setup/backups/{sha}");
                        let existing = self.dir.read(&backup)?;
                        if existing.as_ref().is_some_and(|v| v.sha() != sha) {
                            return Err(Error::msg("Existing backup is corrupt"));
                        }
                        if existing.is_none() {
                            plan.change(
                                &backup,
                                None,
                                Some(Image {
                                    bytes: image.bytes.clone(),
                                    mode: 0o600,
                                }),
                            );
                        }
                        plan.prepared.observed.insert(backup.clone(), existing);
                        plan.backups.push(backup);
                        Some(Original {
                            sha256: sha,
                            mode: image.mode,
                        })
                    } else {
                        None
                    };
                    kind = if original.is_some() {
                        "replace_with_backup"
                    } else {
                        "create"
                    };
                    reason = "Exact file from verified subset";
                    plan.change(&path, current.clone(), Some(desired.clone()));
                    next.files.insert(
                        path.clone(),
                        Entry {
                            sha256: desired.sha(),
                            mode: desired.mode,
                            ownership: file.ownership,
                            original,
                        },
                    );
                }
            } else {
                continue;
            }
            let after = plan
                .prepared
                .changes
                .iter()
                .find(|c| c.path == path)
                .map(|c| &c.after)
                .unwrap_or(&current);
            plan.operations.push(Operation {
                absolute_path: self.root.join(&path),
                before_sha256: current.as_ref().map(Image::sha),
                after_sha256: after.as_ref().map(Image::sha),
                before_mode: current.as_ref().map(|i| i.mode),
                after_mode: after.as_ref().map(|i| i.mode),
                path,
                kind: kind.into(),
                reason: reason.into(),
            });
        }
        next.validate()?;
        let bytes = serde_json::to_vec_pretty(&next)?;
        // Keep state byte-identical when semantic inventory did not change.
        plan.prepared.inventory_after = if next == previous {
            raw
        } else {
            Some(Image { bytes, mode: 0o600 })
        };
        for change in &plan.prepared.changes {
            if change.path.starts_with(".endless-setup/backups/") {
                plan.state_effects.push(Operation {
                    path: change.path.clone(),
                    absolute_path: self.root.join(&change.path),
                    kind: "create_original_backup".into(),
                    reason: "Original bytes are persisted before replacing the target".into(),
                    before_sha256: change.before.as_ref().map(Image::sha),
                    after_sha256: change.after.as_ref().map(Image::sha),
                    before_mode: change.before.as_ref().map(|i| i.mode),
                    after_mode: change.after.as_ref().map(|i| i.mode),
                });
            }
        }
        let changed = plan.prepared.inventory_after != plan.prepared.inventory_before
            || !plan.prepared.changes.is_empty();
        if changed {
            plan.state_effects.push(Operation {
                path: INVENTORY.into(),
                absolute_path: self.root.join(INVENTORY),
                kind: "commit_inventory".into(),
                reason: "Atomic inventory commit, covered by the rollback journal".into(),
                before_sha256: plan.prepared.inventory_before.as_ref().map(Image::sha),
                after_sha256: plan.prepared.inventory_after.as_ref().map(Image::sha),
                before_mode: plan.prepared.inventory_before.as_ref().map(|i| i.mode),
                after_mode: Some(0o600),
            });
            plan.state_effects.push(Operation {
                path: JOURNAL.into(),
                absolute_path: self.root.join(JOURNAL),
                kind: "create_then_remove_journal".into(),
                reason: "Durable before/after images; retained if recovery is required".into(),
                before_sha256: None,
                after_sha256: None,
                before_mode: None,
                after_mode: None,
            });
        }
        let lock = self.dir.read(".endless-setup/lock")?;
        if lock
            .as_ref()
            .is_some_and(|image| image.mode != 0o600 || !image.bytes.is_empty())
        {
            return Err(Error::msg(
                "Execution lock has unexpected content or permissions; refusing to adopt it",
            ));
        }
        plan.state_effects.push(Operation { path: ".endless-setup/lock".into(), absolute_path: self.root.join(".endless-setup/lock"), kind: if lock.is_some() { "acquire_lock" } else { "create_and_acquire_lock" }.into(), reason: "Execution only; persistent private lock. Parent directories may be created but never owned or recursively removed".into(), before_sha256: lock.as_ref().map(Image::sha), after_sha256: lock.as_ref().map(Image::sha).or_else(|| Some(digest(&[]))), before_mode: lock.as_ref().map(|i| i.mode), after_mode: Some(0o600) });
        plan.prepared.executable = plan.blocked.is_empty();
        plan.prepared.seal = digest(&serde_json::to_vec(&plan)?);
        Ok(plan)
    }
    pub fn execute(&self, plan: &Plan) -> Result<Report> {
        self.execute_inner(plan, Fault::None)
    }
    fn execute_inner(&self, plan: &Plan, fault: Fault) -> Result<Report> {
        if self.root != plan.sandbox || !plan.blocked.is_empty() || !plan.prepared.executable {
            return Err(Error::msg("Blocked plan or different sandbox"));
        }
        if digest(&serde_json::to_vec(&plan)?) != plan.prepared.seal {
            return Err(Error::msg("Plan was modified after preparation"));
        }
        let _lock = self.dir.lock()?;
        if self.dir.read(JOURNAL)?.is_some() {
            return Err(Error::msg("Recovery required before execution"));
        }
        if self.dir.read(INVENTORY)? != plan.prepared.inventory_before {
            return Err(Error::msg("Inventory changed since plan"));
        }
        for (path, expected) in &plan.prepared.observed {
            if self.dir.read(path)? != *expected {
                return Err(Error::msg(format!("Target changed since plan: {path}")));
            }
        }
        for change in &plan.prepared.changes {
            if self.dir.read(&change.path)? != change.before {
                return Err(Error::msg(format!(
                    "Target/backup changed: {}",
                    change.path
                )));
            }
        }
        let after = plan.prepared.inventory_after.clone();
        if plan.prepared.changes.is_empty() && after == plan.prepared.inventory_before {
            return Ok(report("unchanged", 0));
        }
        let journal = Journal {
            schema: 1,
            inventory_before: plan.prepared.inventory_before.clone(),
            inventory_after: after.ok_or_else(|| Error::msg("Missing next inventory"))?,
            changes: plan.prepared.changes.clone(),
        };
        validate_journal(&journal)?;
        let journal_image = Image {
            bytes: serde_json::to_vec(&journal)?,
            mode: 0o600,
        };
        if journal_image.bytes.len() > 64 * 1024 * 1024 {
            return Err(Error::msg(
                "Transaction journal exceeds 64 MiB; split the subset",
            ));
        }
        self.dir
            .replace(JOURNAL, &None, &Some(journal_image.clone()))?;
        for (index, change) in journal.changes.iter().enumerate() {
            let outcome = self
                .dir
                .replace(&change.path, &change.before, &change.after);
            if fault.interrupt(index + 1) {
                return Err(Error::msg(
                    "Injected interruption; journal retained for explicit recovery",
                ));
            }
            if let Err(error) = outcome.and_then(|()| {
                if fault.fail(index + 1) {
                    Err(Error::msg("Injected transaction failure"))
                } else {
                    Ok(())
                }
            }) {
                return match self.rollback(&journal, &journal_image) {
                    Ok(()) => Err(Error::msg(format!(
                        "Operation failed; rollback completed: {error}"
                    ))),
                    Err(recovery) => Err(Error::msg(format!(
                        "Operation failed: {error}; recovery pending: {recovery}"
                    ))),
                };
            }
        }
        if let Err(error) = self.dir.replace(
            INVENTORY,
            &journal.inventory_before,
            &Some(journal.inventory_after.clone()),
        ) {
            return match self.rollback(&journal, &journal_image) {
                Ok(()) => Err(Error::msg(format!(
                    "Inventory commit failed; rollback completed: {error}"
                ))),
                Err(recovery) => Err(Error::msg(format!(
                    "Commit failed: {error}; recovery pending: {recovery}"
                ))),
            };
        }
        if fault.interrupt(journal.changes.len() + 1) {
            return Err(Error::msg("Injected interruption after inventory commit"));
        }
        self.dir.replace(JOURNAL, &Some(journal_image), &None)?;
        Ok(report(
            if plan.action == Action::Uninstall {
                "subset_uninstalled"
            } else {
                "subset_applied"
            },
            journal.changes.len(),
        ))
    }
    fn rollback(&self, journal: &Journal, raw: &Image) -> Result<()> {
        validate_journal(journal)?;
        let inventory = self.dir.read(INVENTORY)?;
        if inventory != journal.inventory_before
            && inventory != Some(journal.inventory_after.clone())
        {
            return Err(Error::msg(
                "Inventory changed externally; recovery refuses to overwrite it",
            ));
        }
        // Check the ENTIRE transaction before restoring anything. Unknown data is never overwritten.
        for change in &journal.changes {
            let current = self.dir.read(&change.path)?;
            if current != change.before && current != change.after {
                return Err(Error::msg(format!(
                    "External change blocks recovery: {}",
                    change.path
                )));
            }
        }
        for change in journal.changes.iter().rev() {
            let current = self.dir.read(&change.path)?;
            self.dir.replace(&change.path, &current, &change.before)?;
        }
        self.dir
            .replace(INVENTORY, &inventory, &journal.inventory_before)?;
        self.dir.replace(JOURNAL, &Some(raw.clone()), &None)
    }
    pub fn recover(&self) -> Result<Report> {
        let _lock = self.dir.lock()?;
        let Some(raw) = self.dir.read(JOURNAL)? else {
            return Ok(report("no_recovery_needed", 0));
        };
        let journal: Journal = serde_json::from_slice(&raw.bytes)?;
        self.rollback(&journal, &raw)?;
        Ok(report("recovered_previous_state", journal.changes.len()))
    }
    /// Read-only inventory/resource diagnosis. Never acquires or creates a lock.
    pub fn inspect(&self) -> Result<SandboxInspection> {
        let (inventory, raw) = self.inventory()?;
        let journal = self.dir.read(JOURNAL)?;
        if let Some(raw) = &journal {
            let journal: Journal = serde_json::from_slice(&raw.bytes)?;
            validate_journal(&journal)?;
        }
        let mut files = Vec::new();
        for (path, entry) in &inventory.files {
            let status = match self.dir.read(path) {
                Ok(None) => "missing".into(),
                Ok(Some(image)) if image.sha() == entry.sha256 && image.mode == entry.mode => {
                    "intact".into()
                }
                Ok(Some(_)) => "modified_preserve".into(),
                Err(error) => format!("unsafe_or_unreadable: {error}"),
            };
            let backup = entry
                .original
                .as_ref()
                .map(|value| match self.original(value) {
                    Ok(_) => "verified".into(),
                    Err(error) => format!("invalid: {error}"),
                });
            files.push(InspectedFile {
                path: path.clone(),
                status,
                ownership: entry.ownership,
                original_backup: backup,
            });
        }
        Ok(SandboxInspection {
            sandbox: self.root.clone(),
            inventory_present: raw.is_some(),
            payload_version: inventory.payload_version,
            pending_recovery: journal.is_some(),
            files,
        })
    }
}
#[derive(Debug, Serialize)]
pub struct SandboxInspection {
    pub sandbox: PathBuf,
    pub inventory_present: bool,
    pub payload_version: String,
    pub pending_recovery: bool,
    pub files: Vec<InspectedFile>,
}
#[derive(Debug, Serialize)]
pub struct InspectedFile {
    pub path: String,
    pub status: String,
    pub ownership: Ownership,
    pub original_backup: Option<String>,
}
impl Plan {
    fn change(&mut self, path: &str, before: Option<Image>, after: Option<Image>) {
        if before != after && !self.prepared.changes.iter().any(|c| c.path == path) {
            self.prepared.changes.push(Change {
                path: path.into(),
                before,
                after,
            });
        }
    }
}
fn validate_journal(journal: &Journal) -> Result<()> {
    if journal.schema != 1 || journal.changes.len() > 2048 {
        return Err(Error::msg("Unsupported journal"));
    }
    for raw in journal
        .inventory_before
        .iter()
        .chain(std::iter::once(&journal.inventory_after))
    {
        let inventory: Inventory = serde_json::from_slice(&raw.bytes)?;
        inventory.validate()?;
        if raw.mode != 0o600 {
            return Err(Error::msg("Unsafe inventory permissions in journal"));
        }
    }
    let mut unique = BTreeSet::new();
    for change in &journal.changes {
        let backup = change.path.strip_prefix(".endless-setup/backups/");
        if let Some(hash) = backup {
            if !valid_hash(hash)
                || change.before.is_some()
                || change
                    .after
                    .as_ref()
                    .is_none_or(|v| v.sha() != hash || v.mode != 0o600)
            {
                return Err(Error::msg("Invalid backup journal entry"));
            }
        } else {
            controlled(&change.path)?;
        }
        if !unique.insert(change.path.clone()) {
            return Err(Error::msg("Duplicate journal target"));
        }
        for image in change.before.iter().chain(change.after.iter()) {
            if image.bytes.len() > MAX_FILE || image.mode > 0o777 {
                return Err(Error::msg("Unsafe journal image"));
            }
        }
    }
    no_overlaps(unique.iter())
}
fn report(status: &str, operations: usize) -> Report {
    Report {
        status: status.into(),
        message: WARNING.into(),
        operations,
    }
}
#[derive(Clone, Copy)]
enum Fault {
    None,
    #[cfg(test)]
    FailAfter(usize),
    #[cfg(test)]
    InterruptAfter(usize),
    #[cfg(test)]
    ExitAfter(usize),
}
impl Fault {
    fn fail(self, index: usize) -> bool {
        let _ = index;
        match self {
            #[cfg(test)]
            Self::FailAfter(n) => n == index,
            _ => false,
        }
    }
    fn interrupt(self, index: usize) -> bool {
        let _ = index;
        match self {
            #[cfg(test)]
            Self::ExitAfter(n) if n == index => std::process::exit(87),
            #[cfg(test)]
            Self::InterruptAfter(n) => n == index,
            _ => false,
        }
    }
}

#[derive(Debug, Serialize)]
pub struct DoctorReport {
    pub warning: String,
    pub os: String,
    pub architecture: String,
    pub host_installation: String,
    pub diagnostics: Vec<String>,
    pub dependencies: Vec<Dependency>,
}
#[derive(Debug, Serialize)]
pub struct Dependency {
    pub package: String,
    pub group: String,
    pub installed_in_host_pacman_database: bool,
}
pub fn doctor(manifest: Option<&Path>) -> Result<DoctorReport> {
    let mut diagnostics = vec![
        "Services/dependency installation: NOT IMPLEMENTED".into(),
        "Complete install / integrate existing Hyprland: NOT IMPLEMENTED".into(),
    ];
    let mut dependencies = Vec::new();
    if let Some(path) = manifest {
        let (bundle, _) = load_manifest(path)?;
        diagnostics.push(format!(
            "Payload {}: {} exact files, subset only, digests verified",
            bundle.payload_version,
            bundle.files.len()
        ));
        let absolute = std::path::absolute(path)?;
        let parent = Dir::absolute(
            absolute
                .parent()
                .ok_or_else(|| Error::msg("Manifest parent missing"))?,
        )?
        .confined()?;
        if let Some(asset) = bundle
            .assets
            .iter()
            .find(|asset| asset.role == AssetRole::ArchDependencies)
        {
            let reference = parent
                .read(&asset.source)?
                .ok_or_else(|| Error::msg("Missing Arch reference"))?;
            if reference.sha() != asset.sha256 {
                return Err(Error::msg("Arch reference changed during diagnosis"));
            }
            let reference: serde_json::Value = serde_json::from_slice(&reference.bytes)?;
            let installed: Vec<_> = std::fs::read_dir("/var/lib/pacman/local")
                .map(|rows| {
                    rows.filter_map(|v| v.ok())
                        .filter_map(|v| v.file_name().into_string().ok())
                        .collect()
                })
                .unwrap_or_default();
            for group in ["repository", "aur"] {
                for package in reference[group]
                    .as_array()
                    .into_iter()
                    .flatten()
                    .filter_map(|v| v.as_str())
                {
                    // pacman's directory format is name-version-release; split from the right.
                    let present = installed
                        .iter()
                        .any(|name: &String| name.rsplitn(3, '-').nth(2) == Some(package));
                    dependencies.push(Dependency {
                        package: package.into(),
                        group: group.into(),
                        installed_in_host_pacman_database: present,
                    });
                }
            }
            diagnostics.push("Arch reference snapshot checked read-only against pacman's local directory; no package/version/service readiness claim".into());
        } else {
            diagnostics.push(
                "No bundled Arch dependency reference; host dependency audit incomplete".into(),
            );
        }
    } else {
        diagnostics.push("No manifest selected; payload completeness not checked".into());
    }
    Ok(DoctorReport {
        warning: WARNING.into(),
        os: std::fs::read_to_string("/etc/os-release").unwrap_or_else(|_| "unavailable".into()),
        architecture: std::env::consts::ARCH.into(),
        host_installation: "disabled".into(),
        diagnostics,
        dependencies,
    })
}

#[cfg(test)]
mod tests;
