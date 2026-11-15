"""Independent monitor layouts use real JsonAdapter persistence and live views."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "src/quickshell"
HEADER = '''//@ pragma UseQApplication
import QtQuick
import Quickshell
import qs.services
import qs.modules.shared
import qs.modules.desktop.bar
import qs.modules.settings
ShellRoot {
    id: root
    property int phase: 0
    function expect(value, message) { if (!value) throw new Error(message); }
    function types(view) { return view.entries.map(item => item.type).join(","); }
    property Component settingsType: Component { BarConfig {} }
    PanelWindow {
        implicitWidth: 1600; implicitHeight: 500; exclusiveZone: 0
        ConfiguredBarContent {
            id: a; width: 800; height: implicitHeight; screenName: "TEST-A"
            editing: BarLayout.editing && BarLayout.screenName === screenName
        }
        ConfiguredBarContent {
            id: b; x: 800; width: 800; height: implicitHeight; screenName: "TEST-B"
            editing: BarLayout.editing && BarLayout.screenName === screenName
        }
    }
    Timer {
        interval: 250; repeat: true; running: true
        onTriggered: { try {
            if (!Config.ready) return;
'''
FOOTER = '''
        } catch (error) { console.error("BAR_MONITORS_FAILED", error); Qt.quit(); } }
    }
    Timer { interval: 8000; running: true; onTriggered: {
        console.error("BAR_MONITORS_FAILED timeout"); Qt.quit();
    } }
}
'''


@unittest.skipUnless(os.environ.get("WAYLAND_DISPLAY"), "Monitor bars need Wayland")
class BarPerMonitorTests(unittest.TestCase):
    def test_independent_views_mode_switch_and_cold_start(self):
        with tempfile.TemporaryDirectory(prefix="ai-bar-monitors-") as directory:
            base = Path(directory)
            for name in ("modules", "services", "assets", "scripts", "defaults",
                         "translations", "GlobalStates.qml"):
                (base / name).symlink_to(SOURCE / name)
            env = dict(os.environ, DOTS_SHELL_SOURCE=str(base),
                       XDG_CONFIG_HOME=str(base / "config"),
                       XDG_STATE_HOME=str(base / "state"),
                       XDG_CACHE_HOME=str(base / "cache"))
            launcher = env.get("DOTS_TEST_LAUNCHER")
            command = [launcher] if launcher else [shutil.which("quickshell"), "-p", str(base)]

            def run(body, marker):
                (base / "shell.qml").write_text(HEADER + body + FOOTER)
                result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=14)
                logs = result.stdout + result.stderr
                self.assertEqual(result.returncode, 0, logs)
                self.assertIn(marker, logs)
                for error in ("BAR_MONITORS_FAILED", "TypeError:", "ReferenceError:",
                              "Cannot assign", "Binding loop", "Unable to assign"):
                    self.assertNotIn(error, logs)

            run('''
            if (root.phase === 0) {
                Config.options.bar.layout = {version:2, items:[{key:"clock",type:"clock"}], centerKey:"clock"};
                BarLayout.setIndependent(true);
                BarLayout.begin("TEST-A");
                BarLayout.drop("power", "", 1);
                root.phase++; return;
            }
            if (root.phase === 1) {
                root.expect(root.types(a) === "clock,power" && root.types(b) === "clock",
                    "draft was replicated to the other monitor");
                root.expect(Config.options.bar.layoutsByScreen["TEST-A"] === undefined,
                    "draft saved before Save");
                BarLayout.save();
                BarLayout.begin("TEST-B");
                BarLayout.remove("clock"); BarLayout.drop("resources", "", 0);
                BarLayout.save();
                root.phase++; return;
            }
            if (root.phase === 2) {
                root.expect(root.types(a) === "clock,power" && root.types(b) === "resources",
                    "saving one monitor changed the other");
                BarLayout.setIndependent(false);
                root.phase++; return;
            }
            if (root.phase === 3) {
                root.expect(root.types(a) === "clock" && root.types(b) === "clock",
                    "shared mode lost the original shared layout");
                BarLayout.setIndependent(true);
                root.phase++; return;
            }
            if (root.phase === 4) {
                root.expect(root.types(a) === "clock,power" && root.types(b) === "resources",
                    "mode switch deleted per-monitor layouts");
                BarLayout.begin("TEST-A"); BarLayout.remove("clock"); BarLayout.cancel();
                root.expect(BarLayout.savedFor("TEST-A").items.length === 2, "cancel leaked draft");
                BarLayout.restoreSaved("TEST-A");
                root.expect(!BarLayout.customizedFor("TEST-A") && BarLayout.customizedFor("TEST-B"),
                    "restore affected both monitors");
                BarLayout.begin("TEST-A");
                BarLayout.draft = {version:2,items:[{key:"search",type:"search"}],centerKey:""};
                BarLayout.save();
                root.phase++; return;
            }
            console.log("BAR_MONITORS_SAVED"); Qt.quit();
''', "BAR_MONITORS_SAVED")
            config = base / "config/endless-Impulse/config.json"
            saved = json.loads(config.read_text())["bar"]
            self.assertTrue(saved["independentLayouts"])
            self.assertEqual(saved["layout"]["items"][0]["type"], "clock")
            self.assertEqual(saved["layoutsByScreen"]["TEST-A"]["items"][0]["type"], "search")
            self.assertEqual(saved["layoutsByScreen"]["TEST-B"]["items"][0]["type"], "resources")
            run('''
            root.expect(Config.options.bar.independentLayouts && !BarLayout.editing, "mode was not restored");
            root.expect(root.types(a) === "search" && root.types(b) === "resources",
                "monitor layouts were lost on cold start");
            const first = a.tilesInOrder()[0], second = b.tilesInOrder()[0];
            root.expect(first?.visible && first.width > 0 && second?.visible && second.width > 0,
                "restored modules are not rendered");
            console.log("BAR_MONITORS_RELOADED"); Qt.quit();
''', "BAR_MONITORS_RELOADED")
            self.assertEqual(json.loads(config.read_text())["bar"], saved)
