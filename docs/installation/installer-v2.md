# Experimental native installer — stage 1

**EXPERIMENTAL SANDBOX ONLY.** `runtime/installer` contains `endless-setup`, a
Rust library and executable for testing deployment independently of Quickshell
and Hyprland. This stage deploys a representative subset of resources. It does
not produce a working desktop installation, replace `setup`, manage packages,
prepare PAM, enable systemd units or change the current session.

The distribution direction is a versioned GitHub Release bundle with a native
binary, a declarative manifest and exact payload files. No release has been
published by this work. Arch/AUR, Fedora and Nix distribution integration remain
future work; a working Linux executable is not a claim of distribution support.

## Boundaries carried forward from the audit

The existing installer, Nix package and Hyprland session do not provide equivalent
deployment paths. In particular, installing a Nix profile does not deploy the
Hyprland shortcut hooks or Matugen templates. The new engine does not try to fix
the legacy tree as a side effect of testing its own code.

The core owns validation, planning, inventory, conflicts and transactions. The
CLI and terminal view call that same core. The manifest contains data only; no
shell strings are evaluated and no subprocess copies files. `doctor` does not
install dependencies or activate services.

Complete desktop installation and integration into an existing Hyprland
configuration are separate **future modes**. Neither is implemented by stage 1.
Existing `custom/` files and user preferences must not be treated as replaceable
project source. A manifest entry marked `user` is preserved by the engine's
ownership rules rather than silently promoted to project ownership.

## Build and inspect

Run from the repository root:

```bash
cargo build --release --locked --manifest-path runtime/installer/Cargo.toml
runtime/installer/target/release/endless-setup --help
runtime/installer/target/release/endless-setup --version
```

Build dependencies are Rust crates; Quickshell, Hyprland, an active graphical
session and root privileges are not required to run this installer prototype.
The crate declares Rust 1.88 or newer and uses Linux-specific filesystem APIs.
The release executable still has the platform dependencies of its build target.
A fully static release artifact has to be built and verified separately.

The terminal interface uses the cached libc crate and standard Rust I/O. Ratatui
and crossterm were not available in the local cache, so this stage has a small
terminal view with an accessible text fallback. It does not download a TUI stack
at runtime.

## Sandbox contract

Every deployment command requires `--sandbox DIR` (`--root DIR` is an alias).
The root must already exist as a private directory owned by the invoking user
under canonical `/tmp`. The engine rejects real host destinations, symlinks and
unsafe paths. It never interprets the sandbox argument as permission to deploy
to `$HOME`, `/etc` or service directories.

Payload sources must be relative to the manifest directory. Manifest paths do
not expand environment variables, `~` or shell substitutions. Absolute paths,
parent traversal, links, overlapping destinations and invalid digests are
errors. File access during mutation is anchored to directory handles to prevent
following a swapped symlink outside the sandbox. Hardlinked files are rejected.
Linux `openat2` (kernel 5.6 or newer, available to this process) enforces
`RESOLVE_BENEATH`, `RESOLVE_NO_SYMLINKS` and `RESOLVE_NO_XDEV`. Nested mount/bind
crossings are refused. An unavailable syscall is an error, with no permissive
fallback. The archive builder snapshots Cargo's possibly hardlinked executable
as regular bytes; payload and deployment hardlinks remain forbidden.

Only enumerated files are owned. Parent directories are containers and are not
recorded as exclusive property. Uninstall never recursively removes a directory.
Unrelated files and shared directories remain present.

This prototype assumes an ordinary local Linux filesystem with working atomic
rename, file locking and synchronization. It is not a security boundary against
a malicious process with the same UID, nor a guarantee against disk corruption,
filesystem bugs or hardware power loss. Arbitrary filesystems and hostile
concurrent access need further validation before host deployment can be enabled.

## Operations and states

| Operation/state | Current contract |
| --- | --- |
| `plan` | Read and validate inputs, show exact operations and blockers; no destination or inventory writes. Default action is install; `--action` selects update, repair or uninstall. |
| `--dry-run` | Preview a deployment operation without execution. |
| `install` | Apply the reviewed subset plan inside the sandbox; CLI requires `--yes`. |
| Preexisting managed target | Block by default. `--allow-replace` explicitly opts into a recorded original backup before replacement. |
| Already installed, intact | Idempotent; does not silently adopt unrelated files as its own. |
| Managed file changed externally | Block destructive replacement. The user can inspect/save the file manually; there is no force-overwrite option. |
| `update` | Reconcile old inventory with the new exact file list, including files no longer shipped. Preserve externally modified content. |
| `repair` | Restore supported missing managed resources through the same planner; modified files remain conflicts. |
| `uninstall` | Use inventory and checksums; remove intact owned files or restore their recorded originals; preserve modified files, user data and backups. |
| Pending transaction | Refuse new deployment until recovery has resolved it; a read-only plan never performs recovery implicitly. |
| `recover` | Explicitly resolve the pending sandbox journal; CLI requires `--yes`. Refuse recovery when recorded/current content cannot be reconciled safely. |
| Invalid manifest, inventory or journal | Fail closed with a diagnostic. No heuristic deletion or automatic reset. |
| `doctor` | Read-only compatibility/dependency/resource diagnostic. Dependency and service application are not implemented. |

An original-file backup is part of collision handling and inventory correctness.
It is not a complete user backup or an export feature. Backup/export ZIP,
directory-wide preservation policy and production uninstall recovery remain
separate future work. A bundle ZIP used for distribution is not a personal-data
backup.

Sandbox state lives under `.endless-setup/`: `inventory.json`, `journal.json`, a
persistent execution `lock` and content-addressed `backups/<sha256>` files. The
inventory records file ownership, deployed digests and original backups, not
ownership of parent directories. Backups are retained after uninstall.
Plans list target operations with absolute sandbox paths, before/after digests
and permission modes, plus separate state effects (backups, inventory, journal
and lock). A prepared plan is sealed and checked again immediately before use.
File contents and ordinary permission bits are preserved; ACLs, xattrs, file
timestamps and special permission bits are outside this stage's contract.
An interruption before a temporary file is renamed can leave an inert
`.endless-setup-tmp-*` file. Such leftovers are never treated as owned payload or
automatically deleted. Successful/failed transactions may leave empty container
directories, which are deliberately retained.

User-owned seeds are created only on their first installation. Subsequent update
and repair do not overwrite or recreate them; preexisting user files remain
unowned. Uninstall preserves seeds and drops their inventory entries. Modified
managed files remain in residual inventory so they can be reviewed later.
If a managed file has been explicitly deleted, removing its inventory entry does
not recreate its original predecessor; the original backup remains available.

## CLI and terminal view

The checked-in representative bundle manifest is
`runtime/installer/bundle/manifest.json`. To build a fresh bundle from the current
checkout without collecting the full source tree or Rust build artifacts:

```bash
bundle_workspace=$(mktemp -d /tmp/endless-setup-bundle.XXXXXX)
python3 runtime/installer/tools/build_bundle.py --output "$bundle_workspace/bundle"
manifest="$bundle_workspace/bundle/manifest.json"
```

The builder uses an explicit resource allowlist. A SHA-256 manifest detects
missing or changed payload bytes; a digest is not publisher authentication.
Review the resulting exact file list before testing. Examples below assume
`$manifest` names that valid subset bundle manifest:

The checked-in bundle contains seven representative resources and three
digest-verified reference assets (Arch dependency list, host-service list and
license). Lua and Python files are copied only; installation never executes them.

```bash
runtime/installer/target/release/endless-setup plan \
  --sandbox "$sandbox" --manifest "$manifest" --json
runtime/installer/target/release/endless-setup install \
  --sandbox "$sandbox" --manifest "$manifest" --yes
runtime/installer/target/release/endless-setup plan \
  --sandbox "$sandbox" --manifest "$manifest" --action update
runtime/installer/target/release/endless-setup uninstall \
  --sandbox "$sandbox" --dry-run --json
runtime/installer/target/release/endless-setup doctor --manifest "$manifest" --json
runtime/installer/target/release/endless-setup tui \
  --sandbox "$sandbox" --manifest "$manifest"
```

`--json` writes structured results to stdout and structured errors to stderr.
Blocked plans and unsuccessful commands return a nonzero exit code. Human output
always identifies this as an experimental subset rather than declaring the
desktop installed.

`doctor --sandbox DIR` also inspects inventory, backup references, pending journal
and deployed file status without acquiring a mutation lock or recovering state.
Its JSON result contains `host` and `sandbox`; `sandbox` is null when no root was
selected. Invalid or unsafe state returns an error rather than being reset.

The terminal view provides overview, plan, install, update, repair, uninstall and
doctor entries. Up/Down changes selection, Enter opens the selected view, and Esc
exits from navigation. A replacement option is visible and can be toggled. Every
mutating selection first shows its actual plan, then requires the exact text
`APPLY SANDBOX`. Esc followed by Enter exits from a text prompt. Ctrl-C/Ctrl-D in
raw navigation restore terminal attributes before exit.

`TERM=dumb` selects a numbered text menu. With non-TTY stdin or stdout, `tui`
prints the overview and exits without waiting for input or applying changes.
`--help` and `--version` also work without a terminal or sandbox. Plans still
need the sandbox to exist; preview does not create it.

## Arch VM validation workflow

The user is the principal acceptance tester. First use the VM to validate this
stage's sandbox behavior, without deploying it onto the VM's real XDG paths.
Take a VM snapshot independently of the installer before later host integration
experiments.

1. Copy the checkout or a locally prepared subset bundle into the VM. Keep the
   manifest beside its payload; do not run `setup install` as part of this test.
2. Build the executable using Rust, or copy a binary built for that VM's target.
3. Create a private sandbox with `sandbox=$(mktemp -d /tmp/endless-setup-vm.XXXXXX)`.
   It must not be a link to any real home/configuration directory.
4. Set `manifest` to the bundle manifest's absolute path. Run `doctor --json` and
   `plan --json`; record dependency/resource limitations and planned paths.
5. Execute install only with `--sandbox "$sandbox" --yes`. Inspect the subset and
   inventory, then run the same command again to check idempotence.
6. Put a disposable user-created file at a planned destination in a fresh
   sandbox. Check that the default plan blocks it and that explicit
   `--allow-replace` plans a backup before replacement.
7. Use a second fixture release to test a rename and removal. Modify a deployed
   file manually in the sandbox and verify that update/repair do not silently
   overwrite it.
8. Preview uninstall, then execute it. Check original restoration, preservation
   of modified and unrelated files, and retained shared directories/backups.
9. Exercise pending-journal recovery using the automated isolated fixtures before
   considering any manual interruption test. Recovery must not guess when an
   external edit conflicts with the journal.
10. Save the command results as VM test evidence. Successful subset deployment is
    not successful login, desktop startup, locking or full installation.

Do not redirect any of these operations to `~/.config`, `/etc`, a mounted real
home directory or the VM's active services. This MVP has no option that enables
such deployment.

## Automated verification

```bash
cargo test --locked --manifest-path runtime/installer/Cargo.toml
cargo fmt --check --manifest-path runtime/installer/Cargo.toml
cargo clippy --locked --manifest-path runtime/installer/Cargo.toml -- -D warnings
cargo build --release --locked --manifest-path runtime/installer/Cargo.toml
git diff --check
```

The filesystem tests use unique temporary directories. No test needs sudo, a
package manager, the real home configuration or a graphical session. Fixture CLI
smoke tests complement core tests; human terminal acceptance and real host
integration remain distinct validation tasks. Automated pseudo-terminal
smoke checks exercised Up/Down, Enter, Esc, blocked planning and cancellation of
a valid installation plan. They verified terminal-attribute restoration and no
sandbox writes before confirmation or after cancellation. Human terminal UX and
VM desktop acceptance remain pending.
The repeatable smoke also confirms application through the TUI's explicit
confirmation, using its own disposable pseudo-terminal and sandbox.

Run the repeatable release/subset/archive smoke with:

```bash
python3 -B runtime/installer/tools/smoke.py
```

It builds a fresh seven-file bundle from the allowlist and runs the release
binary only in a unique private `/tmp` fixture. It checks preview immutability,
idempotence, repair, conflicts, uninstall preservation and local archive digests.
Core tests also exit a separate test process while its execution lock is held,
then recover its durable journal. Failure injection is compiled only into tests;
the release CLI has no injection environment variable or flag.

Agent verification on 2026-11-14 used cached dependencies with Cargo offline.
These results describe the experimental engine and temporary fixtures only:

| Check | Result |
| --- | --- |
| `cargo test --locked` | PASS — 41 tests: 32 core, 4 CLI parser, 5 executable integration |
| `cargo fmt --check` | PASS |
| `cargo clippy --locked --all-targets -- -D warnings` | PASS |
| `cargo build --release --locked` | PASS |
| `tools/smoke.py` with release binary | PASS — real subset, PTY cancellation/application, tar.gz/ZIP checksums |
| `git diff --check` and checks of newly created source/document files | PASS |
| Real host installation, services and legacy installer | SKIP — forbidden in this stage |
| Human VM/desktop acceptance | SKIP — pending user validation |
| Static release build, signing and publication | SKIP — future release work |

## Local release packaging skeleton

No release is uploaded. After building the Linux binary, create an archive locally:

```bash
release_workspace=$(mktemp -d /tmp/endless-setup-release.XXXXXX)
python3 -B runtime/installer/tools/package_release.py \
  --binary runtime/installer/target/release/endless-setup \
  --bundle runtime/installer/bundle \
  --version 0.1.0-subset --format tar.gz \
  --output "$release_workspace/archive"
```

`--format zip` uses the same exact manifest payload and reference assets. The
tool emits the executable, bundle, license and `SHA256SUMS`, with regular archive
members only. Existing output directories are refused. These are developer-side
preparation tools requiring exclusive control of their `/tmp` workspace; they
are not archive download/extraction/install machinery. Static linking, signing,
provenance, supported build targets and GitHub release automation remain pending.

## Work deliberately left for later stages

- Full payload coverage, executable permissions and complete runtime assets.
- Signed/published release provenance, verification and download/update channels.
- Complete versus existing-Hyprland deployment modes and explicit custom-file policy.
- Distro-specific dependency/service integration and compatible compositor checks.
- Production backup/export policy and user-facing conflict-resolution workflows.
- Host deployment authorization, broader filesystem validation and VM acceptance.

The legacy `setup`, its uninstall command and the active desktop remain unchanged
by this experimental engine.
