"""Real mouse dragging keeps the source alive and previews layout without saving."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from PIL import Image

SOURCE = Path(__file__).resolve().parents[1] / "src/quickshell"


@unittest.skipUnless(os.environ.get("WAYLAND_DISPLAY"), "Bar dragging needs Wayland")
class BarDragTests(unittest.TestCase):
    def test_preview_gap_pointer_grab_cancel_and_catalog(self):
        with tempfile.TemporaryDirectory(prefix="ai-bar-drag-") as directory:
            base = Path(directory)
            for name in ("modules", "services", "assets", "scripts", "defaults",
                         "translations", "GlobalStates.qml"):
                (base / name).symlink_to(SOURCE / name)
            (base / "shell.qml").write_text('''//@ pragma UseQApplication
import QtQuick
import QtTest
import Quickshell
import Quickshell.Wayland
import qs.services
import qs.modules.shared
import qs.modules.desktop.bar
ShellRoot {
    id: root
    property int phase: 0
    property var source: null
    property real powerX: 0
    property point target: Qt.point(0, 0)
    property string initial: ""
    TestCase { id: mouse; parent: host.contentItem; name: "BarDrag"; when: false }
    function expect(value, message) { if (!value) throw new Error(message); }
    function find(item, name) {
        if (item.objectName === name) return item;
        for (const child of item.children ?? []) {
            const result = find(child, name);
            if (result) return result;
        }
        return null;
    }
    function tile(key) { return bar.tilesInOrder().find(item => item.instanceKey === key); }
    PanelWindow {
        id: host
        implicitWidth: 1200; implicitHeight: bar.implicitHeight; exclusiveZone: 0
        WlrLayershell.namespace: "quickshell:bar-drag-test"
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
        mask: Region {}
        ConfiguredBarContent { id: bar; anchors.fill: parent; editing: BarLayout.editing }
    }
    Timer {
        interval: 450; repeat: true; running: true
        onTriggered: { try {
            if (!Config.ready) return;
            if (root.phase === 0) {
                BarLayout.begin(host.screen.name);
                BarLayout.draft = {version: 2, centerKey: "", items: [
                    {key:"search",type:"search"}, {key:"updates",type:"updates"},
                    {key:"power",type:"power"}, {key:"flex",type:"flex"},
                    {key:"clock",type:"clock"}
                ]};
                root.initial = JSON.stringify(BarLayout.draft);
                root.phase++; return;
            }
            if (root.phase === 1) {
                root.source = root.tile("search");
                root.powerX = root.tile("power").mapToItem(bar, 0, 0).x;
                const strip = root.find(bar, "bar-free-strip");
                root.target = strip.mapToItem(bar, strip.width - 1, strip.height / 2);
                const handle = root.find(root.source, "bar-edit-handle-search");
                mouse.mousePress(handle, handle.width / 2, handle.height / 2, Qt.LeftButton);
                mouse.mouseMove(bar, root.target.x, root.target.y, 30);
                root.phase++; return;
            }
            if (root.phase === 2) {
                root.expect(bar.dragging && bar.hoverOnBar, "drag lost the real mouse grab");
                const preview = root.find(bar, "bar-drag-preview");
                root.expect(preview.visible && preview.opacity < 1 && preview.opacity > 0 &&
                    preview.sourceItem === root.source.presenter && !preview.live,
                    "ghost is not a dimmed snapshot of the real module");
                root.expect(root.source.collapsed && root.source.width < .1, "source still reserves space");
                const gap = root.tile("__drag-gap");
                root.expect(gap && Math.abs(gap.width - bar.dragWidth) < .1, "destination does not reserve module width");
                root.expect(root.tile("power").mapToItem(bar, 0, 0).x < root.powerX - 1,
                    "neighbours did not move to fill the original slot");
                root.expect(JSON.stringify(BarLayout.draft) === root.initial && Config.options.bar.layout === null,
                    "hover changed draft or saved preferences");
                preview.grabToImage(result => result.saveToFile(Quickshell.shellPath("drag.png")));
                root.phase++; return;
            }
            if (root.phase === 3) {
                mouse.mouseRelease(bar, root.target.x, root.target.y, Qt.LeftButton);
                root.expect(!bar.drag && BarLayout.draft.items[BarLayout.draft.items.length - 1].key === "search", "drop did not reorder");
                root.expect(!root.tile("__drag-gap") && root.tile("search"), "drop left a placeholder or lost source");
                root.initial = JSON.stringify(BarLayout.draft);
                bar.pressDrag("power", "power", 100, 20);
                bar.moveDrag(20, 20);
                root.phase++; return;
            }
            if (root.phase === 4) {
                bar.cancelDrag();
                root.expect(JSON.stringify(BarLayout.draft) === root.initial, "cancel committed drag");
                bar.pressDrag("resources", "", 100, 200);
                bar.moveDrag(20, 20);
                root.phase++; return;
            }
            if (root.phase === 5) {
                const preview = root.find(bar, "bar-drag-preview");
                root.expect(preview.sourceItem && preview.sourceItem.widgetType === "resources" &&
                    preview.width === preview.sourceItem.implicitWidth, "catalog preview is not the actual module");
                root.expect(root.tile("__drag-gap"), "catalog drag has no insertion space");
                bar.releaseDrag();
                BarLayout.setCenter("power");
                root.phase++; return;
            }
            if (root.phase === 6) {
                root.expect(BarLayout.draft.items[0].type === "resources", "catalog drop failed");
                root.source = root.tile("power");
                bar.pressDrag("power", "power", 100, 20);
                bar.moveDrag(root.target.x, root.target.y);
                root.phase++; return;
            }
            if (root.phase === 7) {
                const strip = root.find(bar, "bar-free-strip");
                root.expect(root.tile("power") === root.source && !root.source.collapsed,
                    "drag recreated the pinned source");
                root.expect(Math.abs(root.source.x + root.source.width / 2 - strip.width / 2) < .1,
                    "drag moved the exact center anchor");
                bar.cancelDrag();
                root.phase++; return;
            }
            if (root.phase === 8) {
                root.initial = JSON.stringify(BarLayout.draft);
                root.source = root.tile("search");
                const catalog = root.find(bar, "bar-module-catalog");
                root.target = catalog.mapToItem(bar, catalog.width / 2, catalog.height / 2);
                const handle = root.find(root.source, "bar-edit-handle-search");
                mouse.mousePress(handle, handle.width / 2, handle.height / 2, Qt.LeftButton);
                mouse.mouseMove(bar, root.target.x, root.target.y, 30);
                root.phase++; return;
            }
            if (root.phase === 9) {
                root.expect(bar.dragging && bar.hoverOnCatalog && !bar.hoverOnBar,
                    "catalog does not accept a dragged module");
                root.expect(JSON.stringify(BarLayout.draft) === root.initial,
                    "hovering the catalog removed the module before release");
                mouse.mouseRelease(bar, root.target.x, root.target.y, Qt.LeftButton);
                root.expect(!BarLayout.locate("search") && BarLayout.available("search"),
                    "returning a module did not remove it and free its catalog entry");
                root.expect(Config.options.bar.layout === null, "removal saved preferences without Save");
                // Returning a centered module also clears its anchor.
                bar.pressDrag("power", "power", 100, 20);
                bar.moveDrag(root.target.x, root.target.y);
                bar.releaseDrag();
                root.expect(!BarLayout.locate("power") && BarLayout.draft.centerKey === "",
                    "returning a pinned module left a stale anchor");
                BarLayout.cancel();
                root.expect(Config.options.bar.layout === null && !bar.drag, "cancel leaked preferences");
                console.log("BAR_DRAG_OK"); Qt.quit();
            }
        } catch (error) { console.error("BAR_DRAG_FAILED", error); Qt.quit(); } }
    }
    Timer { interval: 12000; running: true; onTriggered: {
        console.error("BAR_DRAG_FAILED timeout"); Qt.quit();
    } }
}
''')
            env = dict(os.environ, DOTS_SHELL_SOURCE=str(base),
                       XDG_CONFIG_HOME=str(base / "config"),
                       XDG_STATE_HOME=str(base / "state"),
                       XDG_CACHE_HOME=str(base / "cache"))
            launcher = env.get("DOTS_TEST_LAUNCHER")
            command = [launcher] if launcher else [shutil.which("quickshell"), "-p", str(base)]
            result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=18)
            logs = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, logs)
            self.assertIn("BAR_DRAG_OK", logs)
            with Image.open(base / "drag.png") as capture:
                pixels = list(capture.convert("RGBA").getdata())
                self.assertGreater(sum(pixel[3] > 0 for pixel in pixels), len(pixels) * .05,
                                   "The drag preview is blank")
                self.assertGreater(len({pixel[:3] for pixel in pixels if pixel[3] > 0}), 2,
                                   "The drag preview has no module details")
            for error in ("BAR_DRAG_FAILED", "TypeError:", "ReferenceError:",
                          "Cannot assign", "Binding loop", "Unable to assign"):
                self.assertNotIn(error, logs)
