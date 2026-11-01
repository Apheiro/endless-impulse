"""Persist and reload bar layout through Quickshell's actual JsonAdapter."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/quickshell"
ITEMS = [
    {"key": "space-before", "type": "flex"},
    {"key": "my-workspaces", "type": "workspaces"},
    {"key": "my-clock", "type": "clock"},
    {"key": "space-after", "type": "flex"},
]


@unittest.skipUnless(os.environ.get("WAYLAND_DISPLAY"), "Quickshell needs Wayland")
class BarLayoutPersistenceTests(unittest.TestCase):
    def test_save_to_disk_and_load_in_new_process(self):
        with tempfile.TemporaryDirectory(prefix="ai-bar-persistence-") as directory:
            home = Path(directory)
            for name in ("modules", "services", "assets", "scripts",
                         "defaults", "translations", "GlobalStates.qml"):
                (home / name).symlink_to(SOURCE / name)
            environment = dict(
                os.environ,
                DOTS_SHELL_SOURCE=str(home),
                XDG_CONFIG_HOME=str(home / "config"),
                XDG_STATE_HOME=str(home / "state"),
                XDG_CACHE_HOME=str(home / "cache"),
                XDG_DATA_HOME=str(home / "data"),
            )
            command = (
                [environment["DOTS_TEST_LAUNCHER"]]
                if environment.get("DOTS_TEST_LAUNCHER")
                else [shutil.which("quickshell"), "-p", str(home)]
            )
            def run(source, marker):
                (home / "shell.qml").write_text(source)
                result = subprocess.run(
                    command, env=environment, capture_output=True,
                    text=True, timeout=15,
                )
                output = result.stdout + result.stderr
                self.assertEqual(result.returncode, 0, output)
                self.assertIn(marker, output)
                self.assertNotIn("BAR_PERSISTENCE_FAILED", output)

            run('''//@ pragma UseQApplication
import QtQuick
import Quickshell
import qs.services
import qs.modules.shared
ShellRoot {
    property int phase: 0
    Timer {
        interval: 200; repeat: true; running: true
        onTriggered: {
            if (!Config.ready) return;
            if (phase === 0) {
                BarLayout.begin(Quickshell.screens[0]?.name);
                BarLayout.draft = {version: 2, items: [
                    {key:"space-before",type:"flex"},
                    {key:"my-workspaces",type:"workspaces"},
                    {key:"my-clock",type:"clock"},
                    {key:"space-after",type:"flex"}
                ], centerKey:"my-clock"};
                BarLayout.save();
                phase = 1;
            } else {
                console.log("BAR_PERSISTENCE_SAVED");
                Qt.quit();
            }
        }
    }
    Timer {interval:8000;running:true;onTriggered:{
        console.error("BAR_PERSISTENCE_FAILED timeout");Qt.quit();
    }}
}
''', "BAR_PERSISTENCE_SAVED")
            config_file = home / "config/artificial-impulse/config.json"
            saved = json.loads(config_file.read_text())["bar"]["layout"]
            self.assertEqual(saved["items"], ITEMS)
            self.assertEqual(saved["centerKey"], "my-clock")

            # A fresh Quickshell process returns a Qt-wrapped array from
            # JsonAdapter; that must not be mistaken for the legacy zone format.
            run('''//@ pragma UseQApplication
import QtQuick
import Quickshell
import qs.services
import qs.modules.shared
ShellRoot {
    Timer {
        interval: 200; repeat: true; running: true
        onTriggered: {
            if (!Config.ready) return;
            const raw = Config.options.bar.layout;
            const restored = BarLayout.saved;
            if (raw?.items?.length !== 4 ||
                restored.items.map(item => item.type).join(",") !==
                "flex,workspaces,clock,flex" ||
                restored.centerKey !== "my-clock") {
                console.error("BAR_PERSISTENCE_FAILED",
                    JSON.stringify(raw), JSON.stringify(restored));
            } else {
                console.log("BAR_PERSISTENCE_RELOADED");
            }
            Qt.quit();
        }
    }
    Timer {interval:8000;running:true;onTriggered:{
        console.error("BAR_PERSISTENCE_FAILED timeout");Qt.quit();
    }}
}
''', "BAR_PERSISTENCE_RELOADED")
            self.assertEqual(json.loads(config_file.read_text())["bar"]["layout"], saved)


if __name__ == "__main__":
    unittest.main()
