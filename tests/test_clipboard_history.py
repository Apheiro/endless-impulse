"""Saved clipboard data survives real cliphist wipes in a disposable database."""
import base64
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "src/quickshell"
spec = importlib.util.spec_from_file_location("clipboard_history", SOURCE / "scripts/clipboard/history.py")
history = importlib.util.module_from_spec(spec)
spec.loader.exec_module(history)
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1kAAAAASUVORK5CYII=")


@unittest.skipUnless(shutil.which("cliphist"), "cliphist is required")
class ClipboardHistoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ai-clipboard-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        wrapper = self.base / "cliphist-fixture"
        wrapper.write_text("#!" + sys.executable + "\nimport subprocess,sys\n"
                           + "sys.exit(subprocess.run(" + repr([shutil.which("cliphist"), "-db-path", str(self.base / "db")])
                           + "+sys.argv[1:]).returncode)\n")
        wrapper.chmod(0o700)
        for name, value in {"DIRECTORY": self.base / "data", "INDEX": self.base / "data/saved.json", "BINARY": str(wrapper)}.items():
            replacement = patch.object(history, name, value)
            replacement.start()
            self.addCleanup(replacement.stop)

    def store(self, payload):
        history.cliphist("store", payload)
        return history.cliphist("list").decode().splitlines()[0].partition("\t")[0]

    def test_saved_text_and_image_survive_clear_and_database_recreation(self):
        with history.locked():
            text = b"Literal 'quotes', %s and $(not-a-command)\nsecond line\n"
            history.pin(self.store(text))
            history.pin(self.store(PNG))
            self.store(b"ordinary history")
            before = history.snapshot()
            self.assertEqual(len(before["pinned"]), 2)
            self.assertEqual(before["removableCount"], 1)
            history.clear()
            after = history.snapshot()
            self.assertEqual(after["pinned"], before["pinned"])
            self.assertEqual(after["removableCount"], 0)
            self.assertEqual({history.decode(key) for key in after["pinned"]}, {text, PNG})
            self.assertEqual(os.stat(history.INDEX).st_mode & 0o777, 0o600)
            self.assertEqual(os.stat(history.DIRECTORY).st_mode & 0o777, 0o700)
            # An external cliphist wipe or cache cleanup must not remove saved data.
            (self.base / "db").unlink()
            self.assertEqual(history.snapshot()["pinned"], before["pinned"])
            self.assertEqual({history.decode(key) for key in before["pinned"]}, {text, PNG})

    def test_unpin_returns_data_to_ordinary_history_and_clear_can_remove_it(self):
        with history.locked():
            history.pin(self.store(b"keep until unpinned"))
            key = history.snapshot()["pinned"][0]
            history.clear()
            history.unpin(key)
            result = history.snapshot()
            self.assertEqual(result["pinned"], [])
            self.assertEqual(result["removableCount"], 1)
            self.assertEqual(history.decode(result["entries"][0]), b"keep until unpinned")
            self.assertFalse(history.payload_path(key).exists())
            history.clear()
            self.assertEqual(history.snapshot()["entries"], [])

    def test_recopying_saved_content_is_not_duplicated(self):
        with history.locked():
            value = self.store(b"saved content")
            history.pin(value)
            history.pin(value)
            self.store(b"another entry")
            self.store(b"saved content")
            result = history.snapshot()
            self.assertEqual(len(result["pinned"]), 1)
            self.assertEqual(len(result["entries"]), 2)
            self.assertEqual(result["removableCount"], 1)

    def test_clear_refuses_to_erase_history_if_saved_copy_is_damaged(self):
        with history.locked():
            history.pin(self.store(b"protected"))
            key = history.snapshot()["pinned"][0]
            history.payload_path(key).write_bytes(b"corrupted")
            self.store(b"still in history")
            with self.assertRaisesRegex(ValueError, "not cleared"):
                history.clear()
            self.assertIn(b"still in history", history.cliphist("list"))

    def test_identifiers_cannot_escape_saved_directory(self):
        for value in ("../saved", "saved-../../file", "1; touch unwanted", "", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                history.decode(value)

    @unittest.skipUnless(os.environ.get("WAYLAND_DISPLAY"), "Clipboard UI needs Wayland")
    def test_qml_save_clear_unpin_and_image_decode(self):
        self.store(b"ordinary fixture")
        self.store(PNG)
        for name in ("modules", "services", "scripts", "assets", "defaults", "translations", "GlobalStates.qml"):
            (self.base / name).symlink_to(SOURCE / name)
        (self.base / "shell.qml").write_text('''//@ pragma UseQApplication
import QtQuick
import Quickshell
import Quickshell.Io
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets
ShellRoot {
    id: root
    property int phase: 0
    property bool decoded: false
    property string imageEntry: ""
    function expect(value, message) { if (!value) throw new Error(message); }
    function find(item, name) {
        if (item.objectName === name) return item;
        for (const child of item.children ?? []) {
            const result = find(child, name);
            if (result) return result;
        }
        return null;
    }
    Process {
        id: decoder
        onExited: code => { root.expect(code === 0, "saved image decode failed"); root.decoded = true; }
    }
    PanelWindow {
        implicitWidth: 600; implicitHeight: 120; exclusiveZone: 0
        ClipboardHistoryTools { id: tools; anchors.fill: parent }
    }
    Timer {
        interval: 150; repeat: true; running: true
        onTriggered: { try {
            if (Cliphist.busy) return;
            if (root.phase === 0) { Cliphist.refresh(); root.phase++; return; }
            root.expect(!Cliphist.error, Cliphist.error);
            if (root.phase === 1) {
                root.expect(Cliphist.entries.length === 2, "fixture history was not loaded");
                const image = Cliphist.entries.find(entry => Cliphist.entryIsImage(entry));
                root.expect(image, "image not recognized");
                Cliphist.togglePin(image); Cliphist.refresh(); Cliphist.refresh();
                root.phase++; return;
            }
            if (root.phase === 2) {
                root.expect(Cliphist.pinned.length === 1 && Cliphist.removableCount === 1, "save failed");
                root.imageEntry = Cliphist.entries[0];
                root.expect(Cliphist.isPinned(root.imageEntry) && Cliphist.entryIsImage(root.imageEntry), "saved image lost its type");
                root.expect(Cliphist.latestEntry !== root.imageEntry, "saved ordering replaced chronological history");
                LauncherSearch.query = Config.options.search.prefix.clipboard;
                root.expect(!LauncherSearch.searchActions.some(action => action.action === "wipeclipboard"), "wipe action remains");
                const entry = LauncherSearch.results.find(entry => entry.rawValue === root.imageEntry);
                root.expect(entry && entry.actions.some(action => action.iconName === "keep_off") &&
                    !entry.actions.some(action => action.iconName === "delete"), "saved actions are not protected");
                const clear = root.find(tools, "clipboard-clear-history");
                root.expect(clear.enabled, "clear button is disabled with ordinary history");
                clear.clicked(); root.phase++; return;
            }
            if (root.phase === 3) {
                root.expect(Cliphist.entries.length === 1 && Cliphist.removableCount === 0 && !Cliphist.historyEntries.length,
                    "clear removed saved data or retained ordinary history");
                decoder.command = Cliphist.cacheCommand(root.imageEntry, Quickshell.shellPath("decoded.png"));
                decoder.running = true; root.phase++; return;
            }
            if (root.phase === 4 && root.decoded) {
                Cliphist.togglePin(root.imageEntry); root.phase++; return;
            }
            if (root.phase === 5) {
                root.expect(!Cliphist.pinned.length && Cliphist.removableCount === 1, "unsave did not return item to history");
                root.find(tools, "clipboard-clear-history").clicked(); root.phase++; return;
            }
            if (root.phase === 6) {
                root.expect(!Cliphist.entries.length && !root.find(tools, "clipboard-clear-history").enabled,
                    "empty history has an active clear button");
                console.log("CLIPBOARD_UI_OK"); Qt.quit();
            }
        } catch (error) { console.error("CLIPBOARD_UI_FAILED", error); Qt.quit(); } }
    }
    Timer { interval: 10000; running: true; onTriggered: { console.error("CLIPBOARD_UI_FAILED timeout"); Qt.quit(); } }
}
''')
        env = dict(os.environ, DOTS_SHELL_SOURCE=str(self.base), DOTS_CLIPHIST_BINARY=history.BINARY,
                   XDG_CONFIG_HOME=str(self.base / "config"), XDG_STATE_HOME=str(self.base / "state"),
                   XDG_CACHE_HOME=str(self.base / "cache"), XDG_DATA_HOME=str(self.base / "ui-data"))
        launcher = env.get("DOTS_TEST_LAUNCHER")
        command = [launcher] if launcher else [shutil.which("quickshell"), "-p", str(self.base)]
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=15)
        logs = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, logs)
        self.assertIn("CLIPBOARD_UI_OK", logs)
        for error in ("CLIPBOARD_UI_FAILED", "TypeError:", "ReferenceError:", "Binding loop", "Unable to assign"):
            self.assertNotIn(error, logs)
        self.assertEqual((self.base / "decoded.png").read_bytes(), PNG)
