# Endless Impulse architecture

Endless Impulse is an installable Linux desktop shell, not a web application.

## Runtime layers

1. **Presentation** — `src/quickshell/modules/`, `shellVariants/` and
   `shell.qml` implement desktop views in QML and JavaScript.
2. **Application state and orchestration** — `src/quickshell/services/`
   exposes reusable reactive services, user settings, session state and actions.
3. **System adapters** — `src/quickshell/scripts/` and
   `config/xdg/config/hypr/` communicate with Hyprland, PipeWire,
   NetworkManager, BlueZ, D-Bus and desktop programs. Python, Lua and Bash
   complement Quickshell, rather than constituting a separate HTTP backend.
4. **Deployment** — `packaging/nix/`, `runtime/`, `installer/`
   and `config/` define immutable application dependencies, mutable host
   integration and deployment targets.

## Quickshell source organization

- `modules/desktop/`: the native Endless Impulse layout, including bar,
  dock, overlays and sidebars.
- `modules/windowsStyle/`: alternative Windows-inspired layout.
- `modules/shared/`: reusable components, appearance tokens and helpers. A single
  `primitives/{common,settings,dialogs,bar}/` tree owns reusable visual/interaction
  contracts; `widgets/` contains higher-level compositions. See
  [UI foundations](../development/primitives.md).
- `modules/settings/`: Settings pages and controls.
- `shellVariants/`: composition roots for the desktop and Windows-style
  families; the saved family IDs remain compatible with earlier versions.
- `services/`: state, configuration and application-wide logic.
- `scripts/`: Python, Bash and JavaScript bridges to operating-system
  services and external tools.

## Important boundaries

- QML resolves its `qs.*` imports relative to the selected shell source.
  Keep `src/quickshell/` internally stable when moving components.
- Quickshell's runtime source is `src/quickshell/` in development. Traditional
  deployment targets `~/.config/quickshell/endless-Impulse/`, while Nix installs a copy
  under `share/dots-hyperland/.config/quickshell/endless-Impulse/`.
- User preferences remain in XDG config/state under `endless-Impulse`.
  Source tree moves must not migrate or overwrite personal preferences.
- Nix pins application dependencies. Host drivers, systemd services, the
  compositor, device permissions and platform hardware remain host concerns.
- `src/quickshell/modules/shared/widgets/shapes` is a Git submodule;
  preserve its upstream history and local changes.
- Do not conflate Quickshell UI components with system adapters. Shared
  appearance and widgets belong in `modules/shared`; reusable state and
  application actions in `services`; external commands in `scripts`.

## Verification

Run `./dev check`, `./dev build`, and targeted integration tests before
shipping. The user validates UI appearance, device functions and permissions
in a real Hyprland session.
