# Icon themes

Settings → Appearance → Icons lists installed themes, previews the selection,
and applies it to the shell, KDE, GTK 3/4 and Qt5ct/Qt6ct. Existing GTK 2 and
xsettingsd preferences are updated too. GSettings is synchronized when available;
any failure is reported separately. Applications with private icon sets may ignore
system preferences; some applications read their theme only when launched.

Preferences live in `$XDG_CONFIG_HOME/artificial-impulse/icons.json`.
`$XDG_DATA_HOME/icons/ArtificialImpulse/index.theme` inherits the selected installed
theme and hicolor, following the [freedesktop icon theme specification](https://specifications.freedesktop.org/icon-theme/).
Only custom images are copied into this overlay. Installed theme files are untouched.

Application overrides accept a theme icon name or a local PNG/SVG/XPM (up to 8 MB).
They use a local desktop entry with a unique icon path so applications sharing an
original icon name remain independent. Default restores the original icon while
preserving later changes to other fields. Images have content-specific paths to
avoid stale Qt image caches. The shell resolves theme paths asynchronously and
watches preferences for changes made by the separate Settings process.

The collapsed **Environments & paths** section opens each configuration file.
The wallpaper/colors page also lists Matugen outputs from the user's own
`matugen/config.toml`, shell preferences and generated terminal palettes.
Unavailable files remain visible but disabled. GSettings uses a dconf database;
its directory is shown when present.

Before applying, the helper backs up affected files under
`$XDG_STATE_HOME/artificial-impulse/icon-backups/`. Each backup contains a
`manifest.json` mapping original paths to numbered copies (null means the file
was previously absent). File writes roll back together on failure. GSettings is
applied afterward and reports partial failure without hiding the saved changes.

Development: `scripts/icons/themes.py snapshot` is read-only. `preview` and
`apply` take JSON on stdin. Backend tests use temporary XDG roots; the QML
workflow test also uses the memory GSettings backend and verifies live refresh
from another process. No theme is applied automatically just by opening Settings.
