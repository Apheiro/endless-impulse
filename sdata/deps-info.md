# Dependencies

The source of truth for Arch installations is `dependencies/arch.json`:
ordinary repository and AUR packages, without project-specific metapackages or
a pinned fork of Quickshell. Query it through `dependencies.py`.

- **Desktop:** Hyprland/Wayland, Quickshell and Qt 6/QML.
- **Interface:** Qt compatibility/image modules, Kirigami, syntax highlighting,
  fonts, icons, cursor and GTK/Qt themes.
- **Integration:** PipeWire/WirePlumber, NetworkManager, Bluetooth, D-Bus,
  notifications, portals, authentication and power services.
- **Utilities:** Matugen, clipboard, screenshot/recording, brightness, media,
  OCR/translation and terminal tools.
- **Python:** `uv/requirements.txt` retains the existing locked environment.
- **Formulas:** Node.js with upstream MathJax and local font assets; exact npm
  versions and integrity hashes are in `math/package-lock.json`. No MicroTeX
  fork, `/opt/MicroTeX` installation or network access is needed to render.

`nix/package.nix` and `nix/runtime.nix` at the repository root describe the
independent application runtime. The root `flake.lock` pins its Nixpkgs snapshot
and bundled shape library. Updating Arch's Qt does not replace Nix's Qt.

Artificial Impulse uses `artificial-impulse` for configuration and shortcut state.
The legacy configuration aliases and Python environment variable remain
compatibility interfaces. External package names and license notices are retained.
