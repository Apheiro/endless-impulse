# Shortcut editor

Settings → Shortcuts edits the triggers registered through `hl.bind` while this
project's Hyprland configuration loads, including generated workspace shortcuts
and custom bindings. Bindings with the same trigger and submap move together,
preserving callbacks, flags and fallback actions. Application-internal shortcuts
are outside this editor's scope.

## Development and testing

Use a test user/session with the project's dependencies and configurations.
The updated `config/xdg/config/hypr/hyprland.lua` and
`config/xdg/config/hypr/hyprland/services/shortcuts.lua` must be deployed together to
that user's Hyprland configuration. Reload Hyprland in that test session, then
launch Settings directly from the repository:

```bash
quickshell -p ./src/quickshell/settings.qml
```

Running the QML alone does not activate the Lua integration. The page explains
this when no catalog is available. Merely opening the page does not apply edits.

Search an action, choose Edit, enter a combination such as `SUPER + SHIFT + E`,
and Save & apply. Saving reloads Hyprland; invalid syntax or a reload error restores
the previous saved overrides. Exact key combinations, modifier aliases and
universal-submap conflicts are checked; physical-keycode versus keysym collisions
depend on the keyboard layout and should be tested manually.

User acceptance checks: change an app shortcut, a multi-action shell shortcut,
a workspace shortcut and a mouse shortcut; verify behavior, conflict messages,
persistence after reload and Restore default. The user is the principal tester.

## Storage and automated checks

- `$XDG_CONFIG_HOME/artificial-impulse/shortcuts.lua`: generated overrides, loaded
  as data in an empty Lua environment. Do not hand-edit this file.
- `$XDG_STATE_HOME/artificial-impulse/shortcuts-catalog.json`: catalog regenerated
  when the integrated Hyprland configuration loads.
- XDG directories default to `~/.config` and `~/.local/state`.
- Python 3 handles persistence and reload; libxkbcommon validates keysyms.

```bash
python3 -m unittest discover -s tests -v
```

Tests use temporary directories, inert Lua dispatchers and mocked reloads; they
do not change the active desktop.

## Compact editor

The Settings editor groups every binding under collapsible categories. Explicit
Hyprland description prefixes take precedence; unlabeled bindings inherit the
`--##!` section of their source file. Unknown/custom sources remain available.
This category metadata never changes the registered key, callback or bind flags.
Searching matches categories, descriptions, triggers and submaps and expands the
matching groups. A selected row contains its editor; linked actions stay together.

`ShortcutSymbols.js` supplies the shared modifier, function-key, mouse and media
labels used by the shortcut guide and `ShortcutKeycaps.qml`. The editor displays
exact numbered/keycode triggers instead of the guide's generalized examples.
Guide appearance controls are folded away by default.

The file and folder buttons use paths reported by the helper. Only customized
bindings are written to `shortcuts.lua`; the file button is enabled after the first
customization creates it. Right-click either button to copy its path.
