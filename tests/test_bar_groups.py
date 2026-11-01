"""Exercise grouping through actual layout, visibility and editor changes."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "src/quickshell"


@unittest.skipUnless(os.environ.get("WAYLAND_DISPLAY"), "Bar groups need Wayland")
class BarGroupsTests(unittest.TestCase):
    def test_neighbours_caps_padding_and_transparency(self):
        with tempfile.TemporaryDirectory(prefix="ai-bar-groups-") as directory:
            base = Path(directory)
            for name in ("modules", "services", "assets", "scripts", "defaults",
                         "translations", "GlobalStates.qml"):
                (base / name).symlink_to(SOURCE / name)
            (base / "shell.qml").write_text('''//@ pragma UseQApplication
import QtQuick
import Quickshell
import qs.services
import qs.modules.shared
import qs.modules.desktop.bar
ShellRoot {
    id: root
    property int phase: 0
    function expect(value, message) { if (!value) throw new Error(message); }
    function find(item, name) {
        if (item.objectName === name) return item;
        for (const child of item.children ?? []) {
            const match = find(child, name);
            if (match) return match;
        }
        return null;
    }
    function module(key) { return find(bar, "bar-presenter-" + key); }
    function check(key, before, after) {
        const host = module(key), item = host.moduleItem;
        expect(host.visible && host.width > 0, "module hidden: " + key);
        expect(item.joinedBefore === before && item.joinedAfter === after,
            "wrong neighbours: " + key + " " + item.joinedBefore + "/" + item.joinedAfter);
        const surface = find(item, "bar-module-surface");
        expect(surface.topLeftRadius === (before ? Math.min(surface.radius, Appearance.rounding.unsharpen) : surface.radius),
            "wrong left cap: " + key);
        expect(surface.topRightRadius === (after ? Math.min(surface.radius, Appearance.rounding.unsharpen) : surface.radius),
            "wrong right cap: " + key);
        expect(surface.y >= Appearance.sizes.hyprlandGapsOut + Appearance.sizes.barModuleInset,
            "module paints over floating bar padding");
        expect(surface.y + surface.height <= host.height - Appearance.sizes.hyprlandGapsOut - Appearance.sizes.barModuleInset,
            "module paints over bottom padding");
        expect(surface.color.a < 1, "opaque module: " + key);
        expect(!root.find(item, "bar-module-separator").visible,
            "Pills paints a line instead of a gap");
    }
    PanelWindow {
        implicitWidth: 1200; implicitHeight: bar.implicitHeight; exclusiveZone: 0
        ConfiguredBarContent { id: bar; anchors.fill: parent; editing: BarLayout.editing }
    }
    Timer {
        interval: 300; repeat: true; running: true
        onTriggered: { try {
            if (!Config.ready) return;
            if (root.phase === 0) {
                Config.options.bar.cornerStyle = 1;
                Config.options.bar.borderless = false;
                Config.options.bar.showBackground = true;
                Config.options.bar.weather.enable = false;
                Config.options.bar.layout = {version: 2, centerKey: "power", items: [
                    {key:"search",type:"search"}, {key:"hidden",type:"weather"},
                    {key:"power",type:"power"}, {key:"clock",type:"clock"}
                ]};
                root.phase++; return;
            }
            if (root.phase === 1) {
                root.check("search", false, true);
                root.check("power", true, true);
                root.check("clock", true, false);
                // The transparent gap also survives across the center anchor.
                const left = root.module("search"), right = root.module("power");
                const a = root.find(left.moduleItem, "bar-module-surface");
                const b = root.find(right.moduleItem, "bar-module-surface");
                root.expect(Math.abs(b.mapToItem(bar, 0, 0).x - a.mapToItem(bar, a.width, 0).x - bar.itemSpacing) < .1,
                    "group surfaces cover their transparent gap");
                BarLayout.begin(Quickshell.screens[0].name);
                BarLayout.remove("hidden");
                BarLayout.setCenter("");
                BarLayout.drop("spacer", "", 1);
                root.phase++; return;
            }
            if (root.phase === 2) {
                root.check("search", false, false);
                root.check("power", false, true);
                root.check("clock", true, false);
                BarLayout.moveBy("clock", -1);
                root.phase++; return;
            }
            if (root.phase === 3) {
                root.check("clock", false, true);
                root.check("power", true, false);
                BarLayout.drop("separator", "", 3);
                root.phase++; return;
            }
            if (root.phase === 4) {
                root.check("clock", false, false);
                root.check("power", false, false);
                BarLayout.save();
                root.phase++; return;
            }
            root.check("clock", false, false);
            root.check("power", false, false);
            console.log("BAR_GROUPS_OK"); Qt.quit();
        } catch (error) { console.error("BAR_GROUPS_FAILED", error); Qt.quit(); } }
    }
    Timer { interval: 8000; running: true; onTriggered: {
        console.error("BAR_GROUPS_FAILED timeout"); Qt.quit();
    } }
}
''')
            env = dict(os.environ, DOTS_SHELL_SOURCE=str(base),
                       XDG_CONFIG_HOME=str(base / "config"),
                       XDG_STATE_HOME=str(base / "state"),
                       XDG_CACHE_HOME=str(base / "cache"))
            launcher = env.get("DOTS_TEST_LAUNCHER")
            command = [launcher] if launcher else [shutil.which("quickshell"), "-p", str(base)]
            result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=15)
            logs = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, logs)
            self.assertIn("BAR_GROUPS_OK", logs)
            for error in ("BAR_GROUPS_FAILED", "TypeError:", "ReferenceError:",
                          "Cannot assign", "Binding loop", "Unable to assign"):
                self.assertNotIn(error, logs)
