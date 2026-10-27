# Artificial Impulse — Locked desktop runtime

`flake.lock` fixes the Nixpkgs snapshot and shape library. Nixpkgs supplies
ordinary upstream Quickshell and a matching Qt; no illogical-impulse packages
or Home Manager configuration are required. MathJax uses its own npm lock and
Nix content hash. Python and command-line tools belong to the same locked tree.

## Development

Install Nix, initialize its store/daemon as required by your distribution, and
clone this repository including submodules. On Arch, Nix is available as `nix`
and its socket can be enabled with `sudo systemctl enable --now nix-daemon.socket`.

```bash
./dev build
./dev restart
./dev settings
./dev check
```

`./dev restart` stops only the shell for this repository's configuration and
starts it with Nix dependencies. QML remains editable in the repository and
reloads live. Other shell configurations are separate instances; close them
before running this one. `./dev stop` closes the development instance.

Keyboard IPC uses `dots-shell` to find the active shell, instead of assuming its
configuration is named `ii` or `end4-pC`. The main shell registers its configuration,
Quickshell binary and locked launcher in `$XDG_STATE_HOME/dots-hyperland/runtime.json`.
`dots-shell health` checks its real IPC endpoint; `dots-shell restart` and
`dots-shell settings` preserve that runtime and source path. The Hyprland
keybind configuration detects the profile's `dots-shell` automatically.

Tray items are discovered dynamically through StatusNotifierItem. Quickshell
shares an existing watcher (including kded6) rather than killing it. An optional
XEmbed bridge covers legacy X11 icons. Inspect registered/pinned/overflow items
with `dots-shell ipc tray status`; passive-item filtering and pinning still obey
the user's tray preferences. Applications must publish an icon to appear.

Changes are intentionally uncommitted until the user requests a commit. New
files referenced by Nix must be known to Git; `git add -N <path>` is sufficient
and does not commit their contents.

## Installation

```bash
nix --extra-experimental-features 'nix-command flakes' profile install .#default
dots-hyperland
dots-hyperland-settings
```

The installed launchers use an immutable copy of the QML. Installing the package
does not replace personal configurations, configure host services or start the
shell automatically. Existing preferences stay in their current locations.

Hyprland and its matching `hyprctl`, GPU drivers, PipeWire/WirePlumber,
NetworkManager/Bluetooth services, portals, authentication and PAM screen locking
are host requirements. A new machine also needs the project's Hyprland
configuration/integration. Host drivers and protocol compatibility cannot be
frozen by the application lock file. The launcher includes a host NVIDIA bridge
that exposes only driver libraries through a private cache directory; Mesa uses
the bundled driver paths. On unusual layouts set `DOTS_NVIDIA_LIBDIR`. To use an
external graphics bridge set `DOTS_HOST_GRAPHICS=off`. This has been tested on
Arch with NVIDIA; AMD/Intel and other distributions still need hardware testing.
Do not add all of `/usr/lib` to `LD_LIBRARY_PATH`, which would mix the bundled Qt
with the system Qt.

## Updates and rollback

Update dependencies deliberately with `nix flake update`, rebuild and run checks,
then have the principal tester validate shortcuts, apps, panels, audio, captures,
themes and formulas before releasing. Profile installations support
`nix profile rollback`; keep previous generations until acceptance testing passes.

The supported/tested architecture is x86_64 Linux. An aarch64 output is provided
but needs testing on that hardware. The older experimental Home Manager installer
has been replaced by this root flake.
