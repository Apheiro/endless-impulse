# Clipboard history

Super+V opens the clipboard results. Each entry offers Copy and Save; saved
entries show Unsave instead of Delete. Clear history removes ordinary cliphist
entries while keeping saved entries. Unsave returns the data to ordinary history,
where Clear history or Delete can remove it. The launcher action `/wipeclipboard`
has been removed.

`services/Cliphist.qml` serializes list and mutation requests through
`scripts/clipboard/history.py`. The helper uses argument arrays and binary stdin,
never shell interpolation of clipboard contents. Text and image payloads are
stored intact. Image previews and AI attachments use the same decoder.

Saved entries live in `$XDG_DATA_HOME/artificial-impulse/clipboard` (normally
`~/.local/share/artificial-impulse/clipboard`): `saved.json` indexes private
SHA-256-addressed payload files. They survive cliphist eviction, wipe and cache
cleanup. Payloads are written before their index; Clear history verifies saved
copies before touching cliphist. The directory is private (0700), files 0600.

The search view lists saved entries first, with duplicate ordinary entries
suppressed by payload hash. A separate chronological list feeds last-copy
integrations and superpaste, so saving an older entry does not change those
features. Both shell variants share the same toolbar and saved data.

`tests/test_clipboard_history.py` uses a disposable real cliphist database. It
checks text/image preservation, wipes, cache loss, unpinning, duplicate suppression,
damaged-copy protection, QML actions, and saved-image decoding without modifying
the user's clipboard or history.
