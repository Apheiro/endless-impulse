# Dependencies

The source of truth for Arch installations is `installer/dependencies/arch.json`:
ordinary repository and AUR packages, without project-specific metapackages or
a pinned fork of Quickshell. Query it through `installer/dependencies.py`.

- **Desktop:** Hyprland/Wayland, Quickshell and Qt 6/QML.
- **Interface:** Qt compatibility/image modules, Kirigami, syntax highlighting,
  fonts, icons, cursor and GTK/Qt themes.
- **Integration:** PipeWire/WirePlumber, NetworkManager, Bluetooth, D-Bus,
  notifications, portals, authentication and power services.
- **Utilities:** Matugen, clipboard, screenshot/recording, brightness, media,
  OCR/translation and terminal tools.
- **Python:** `runtime/python/requirements.txt` retains the existing locked environment.
- **Formulas:** Node.js with upstream MathJax and local font assets; exact npm
  versions and integrity hashes are in `runtime/math/package-lock.json`. No MicroTeX
  fork, `/opt/MicroTeX` installation or network access is needed to render.

`packaging/nix/package.nix` and `packaging/nix/runtime.nix` at the repository root describe the
independent application runtime. The root `flake.lock` pins its Nixpkgs snapshot
and bundled shape library. Updating Arch's Qt does not replace Nix's Qt.
`nix run .#services -- --apply` prepares the declared host services on
Arch/systemd, also used by the setup stage of `./setup install --via-nix`.
See `packaging/nix/services/arch.json` and `packaging/nix/README.md`; graphics drivers are excluded.

Artificial Impulse uses `artificial-impulse` for configuration and shortcut state.
The legacy configuration aliases and Python environment variable remain
compatibility interfaces. External package names and license notices are retained.

Video recording uses upstream `gpu-screen-recorder` (host GPU binary preferred,
pinned Nix fallback bundled). The `record.sh` compatibility launcher remains.
See [recording integration](../features/recording.md) for permissions and runtime behavior.

The native audio panel uses PipeWire client tools (`pw-dump`, `pw-link`,
`pw-metadata`), `pactl` via pipewire-pulse, and native Quickshell level meters.
Nix bundles the clients and uses the host audio services. See [audio integration](../features/audio.md).

Bluetooth management uses the host BlueZ service, Quickshell Bluetooth and a
Python GObject/GIO agent. BlueDevil is no longer a shell dependency. See
[Bluetooth integration](../features/bluetooth.md) for pairing and agent behavior.

Network management uses native libnm/GIO and the host NetworkManager, replacing
Plasma-NM. Nix includes libnm introspection. See [network integration](../features/network.md)
for profiles, credentials, rollback and optional VPN/hotspot dependencies.

About includes a read-only dependency map grouped by function. It shows current
requirements and feature integrations, with Arch package names as a reference;
it is not an inventory of installed software and excludes retired packages.
Source links point to the actual checkout manifests when available. Installed
bundles use `defaults/dependencies.json`; Nix regenerates that snapshot at build
time. After changing the manifest or grouping metadata, regenerate the committed
fallback with:

```bash
python3 src/quickshell/scripts/system/dependencies.py --root . --snapshot > src/quickshell/defaults/dependencies.json
```

Tailscale uses the host `tailscaled` daemon and a bundled/host `tailscale` CLI.
The native panel discovers CLI options at runtime and requires operator rights
or an explicit Polkit operation for privileged changes. See
[Tailscale integration](../features/tailscale.md).
