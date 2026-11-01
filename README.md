# Artificial Impulse

Artificial Impulse is a customizable Hyprland/Wayland shell and a fork of
[illogical-impulse](https://github.com/end-4/dots-hyprland).
It uses ordinary upstream packages and an independent, locked Nix runtime.


## Repository architecture

The development source tree is separate from the paths installed on Linux.
Quickshell QML and JavaScript execute inside the desktop process; Python,
Lua and shell scripts integrate with Hyprland and system services. Nix packages
the application; the installer deploys XDG configuration and prepares the host.

| Directory | Responsibility |
| --- | --- |
| [src/quickshell/](src/quickshell/) | Quickshell UI, state/services and system adapters: `modules/{desktop,windowsStyle,shared,settings}` |
| [config/xdg/](config/xdg/) | Deployable XDG configuration and data |
| [config/variants/](config/variants/) | Optional distribution and theme variants |
| [installer/](installer/) | Host integration, distribution dependencies, setup commands |
| [runtime/](runtime/) | MathJax and Python dependency specifications |
| [packaging/nix/](packaging/nix/) | Locked package and service implementation |
| [tests/](tests/) | Automated tests |
| [docs/](docs/) | Architecture, feature and development documentation |

See [architecture and boundaries](docs/architecture/overview.md) and
[repository layout and deployment mappings](docs/development/repository-layout.md).


## Develop

With a functioning Hyprland session and Nix initialized:

```bash
./dev build
./dev restart
./dev settings
./dev check
```

QML changes reload from the repository. Dependencies are fixed by `flake.lock`;
formulas use locally installed MathJax assets rather than the MicroTeX fork.
Do not run another shell configuration alongside this one.

See [packaging/nix/README.md](packaging/nix/README.md) for installation, host requirements, graphics,
updates and rollback. Installations from a private repository require access to
that repository. The package does not overwrite your personal configurations.

For native Arch dependencies, see [installer/distros/arch/README.md](installer/distros/arch/README.md).
For shortcut editing, see [docs/development/shortcuts-development.md](docs/development/shortcuts-development.md).
For displays, windows and input configuration, see [docs/features/desktop-settings.md](docs/features/desktop-settings.md).
Feature priorities and validation status are tracked in [ROADMAP.md](ROADMAP.md).
The user is the principal acceptance tester. Changes accumulate until a commit
is explicitly requested.

## Preferences

Settings are stored in `$XDG_CONFIG_HOME/artificial-impulse` and shortcut state
in `$XDG_STATE_HOME/artificial-impulse`. Launchers migrate the old directories
without overwriting existing destinations and retain legacy path aliases.
Existing keyring entries remain readable; new entries use `artificial-impulse`.
The saved shell-family IDs `ii` and `waffle` and the legacy Python environment
variable remain compatibility identifiers. The installed configuration is named
`artificial-impulse`; development source lives in `src/quickshell/`.
External package names and license notices are unchanged.

## Dock minimization

Click an application's focused window in the dock to minimize it. Click its icon
again to restore it; inactive windows are focused first. Apps with several windows
can also be minimized or restored individually from the dock's previews.
Minimized icons remain visible with hollow indicators. Their original workspace
is remembered across shell reloads in session-scoped local state.

This uses `special:artificial-minimized`, separate from the Super+S scratchpad.
For recovery, `python3 src/quickshell/scripts/hyprland/minimize.py restore-all`
restores parked windows without touching the scratchpad. Pinned or grouped windows
must be unpinned/ungrouped first; the dock reports the reason if an action fails.

Dock previews request a single reduced capture, then update about once per second
only while visible. Before minimizing, the last image is retained in a shared RAM
cache (up to 24 thumbnails, each at most 300 × 200). Capture sources are detached
after each image; minimized windows use the static thumbnail. Images are never
written to disk by the dock, and closing a window or locking the screen clears
its cached images. The cache is transient across shell reloads.

Icon themes and per-application overrides are available in Settings → Appearance → Icons.
The collapsed Environments & paths section opens the configuration files. See
[icon theme integration](docs/features/icon-themes.md) for the managed paths and behavior.

About includes a searchable installation map: expand branches, open locations or
copy paths. Shared locations appear once with their uses grouped together. The
map reads active shell paths, configured capture destinations and environment
configuration paths; missing locations are dimmed and are never created by browsing.

Video capture uses GPU Screen Recorder, with a right-click region/full-screen menu,
an elapsed-time indicator, a persistent region border and complete recording
preferences. See [recording controls and configuration](docs/features/recording.md).

## Audio

Click the speaker to open the bottom-centered PipeWire panel: application mixing,
inputs/outputs, profiles, port routing and session diagnostics. See
[audio integration](docs/features/audio.md) for controls, dependencies and runtime behavior.

## Bluetooth

The Bluetooth icon opens a centered native BlueZ panel, including pairing PINs
and confirmation prompts. See [Bluetooth integration](docs/features/bluetooth.md) for
controls, discovery limits and dependencies.
