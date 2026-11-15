"""Load real native page/primitives and JSON worker with isolated state, offscreen."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/quickshell"


class HardwareQmlTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("quickshell"), "Quickshell unavailable")
    def test_page_real_backend_and_draft_roundtrip(self):
        with tempfile.TemporaryDirectory(prefix="ei-hw-") as temporary:
            base = Path(temporary)
            def write(name, text):
                path = base / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            def copy(name): write(name, (SOURCE / name).read_text())
            (base / "scripts").symlink_to(SOURCE / "scripts")
            for name in ("HardwareConfig", "SettingsPage", "SettingsSection", "SettingsCatalog"):
                copy("modules/settings/" + name + ".qml")
            for path in (SOURCE / "modules/settings/hardware").glob("*.qml"):
                copy("modules/settings/hardware/" + path.name)
            copy("services/Hardware.qml")
            for name in ("SettingsCard", "ContentPage"):
                copy("modules/shared/primitives/settings/" + name + ".qml")
            for name in ("StyledText", "MaterialSymbol", "MaterialTextField", "RippleButton", "StyledFlickable", "StyledScrollBar", "StyledSwitch", "StyledComboBox", "StyledListView", "StyledRectangularShadow", "PointingHandInteraction", "SegmentedControl"):
                copy("modules/shared/primitives/common/" + name + ".qml")
            copy("modules/shared/widgets/RippleButtonWithIcon.qml")
            copy("modules/shared/functions/ColorUtils.qml")
            write("services/Translation.qml", 'pragma Singleton\nimport QtQuick\nQtObject { function tr(text) { return text; } }')
            write("modules/shared/Config.qml", 'pragma Singleton\nimport QtQuick\nQtObject { property var options: ({interactions:{scrolling:{touchpadScrollFactor:100,mouseScrollFactor:50,mouseScrollDeltaThreshold:120,fasterTouchpadScroll:false}}}) }')
            appearance = (SOURCE / "modules/shared/Appearance.qml").read_text()
            colors = {key: "#eeeeee" if key.startswith("colOn") else "#aaccff" if key == "colPrimary" else "#bbbbbb" if key == "colSubtext" else "#333333" for key in re.findall(r"property color (col\w+):", appearance)}
            m3 = dict(re.findall(r'property color (m3\w+): "(#[^"]+)"', appearance), darkmode=True)
            tokens = dict(colors=colors, m3colors=m3,
                          font=dict(family=dict(main="Sans", numbers="Sans", iconMaterial="Material Symbols Rounded", iconNerd="Sans"), pixelSize=dict(small=14, smaller=12, normal=15, larger=18), variableAxes=dict(main={})),
                          rounding=dict(small=8, normal=12, large=16, full=1000, unsharpenmore=8),
                          sizes=dict(textInputHorizontalPadding=12, textInputVerticalPadding=8, textInputMinimumHeight=40, elevationMargin=16),
                          animationCurves=dict(standardDecel=[0,0,1,1,1,1], expressiveFastSpatialDuration=0, expressiveFastSpatial=[0,0,1,1,1,1]))
            animation = '''property QtObject animation: QtObject {
                property QtObject elementMoveFast: QtObject { id: fast; property int duration: 0; property int type: Easing.Linear; property var bezierCurve: [0,0,1,1,1,1]; property Component colorAnimation: ColorAnimation { duration: 0 }; property Component numberAnimation: NumberAnimation { duration: 0 } }
                property QtObject elementMoveEnter: fast
                property QtObject scroll: fast
            }'''
            write("modules/shared/Appearance.qml", 'pragma Singleton\nimport QtQuick\nQtObject {\n'
                  + ''.join('property var ' + key + ':' + json.dumps(value) + '\n' for key, value in tokens.items())
                  + animation + '\nfunction animationDuration(ms) { return 0; } }')
            write("shell.qml", '''//@ pragma UseQApplication
//@ pragma Env QT_QUICK_CONTROLS_STYLE=Basic
import QtQuick
import QtQuick.Window
import QtTest
import Quickshell
import qs.modules.settings
import qs.services
ShellRoot {
    id: test
    Window { id: view; visible: true; width: 1250; height: 850; color: "#202020" }
    TestCase { id: pointer; parent: view.contentItem; name: "HardwarePointer"; when: false }
    property int phase: 0
    property var page: null
    property string selected: ""
    SettingsCatalog { id: catalog }
    property Component pageType: HardwareConfig { width: parent.width; height: parent.height }
    function find(item, name) {
        if (item.objectName === name) return item;
        for (const child of item.children || []) { const result = find(child, name); if (result) return result; }
        return null;
    }
    function click(name) {
        const item = find(test.page, name);
        expect(!!item, "Missing control " + name);
        if (name.startsWith("hardware-driver") || name.startsWith("hardware-rule-") || name === "hardware-return-source") {
            const scroller = name.startsWith("hardware-driver") ? test.page.inspector : test.page.ruleEditor;
            scroller.contentY = Math.max(0, item.mapToItem(scroller.contentItem, 0, 0).y - 20);
        }
        pointer.mouseClick(item, Math.max(1,item.width/2), Math.max(1,item.height/2), Qt.LeftButton);
    }
    function expect(condition, message) { if (!condition) throw new Error(message); }
    Timer {
        interval: 100; running: true; repeat: true
        onTriggered: {
            try {
                if (Hardware.busy) return;
                if (test.phase === 0) {
                    const hardwareIndex = catalog.pages.findIndex(p => p.component === "HardwareConfig.qml");
                    test.expect(hardwareIndex >= 0 && catalog.pages[hardwareIndex].group === "System", "Hardware not registered in System");
                    test.expect(catalog.matches(hardwareIndex, "administrador dispositivos"), "Hardware search missing");
                    test.page = test.pageType.createObject(view.contentItem);
                    test.expect(!!test.page, "Page failed to instantiate");
                    test.phase++;
                } else if (test.phase === 1) {
                    if (!Hardware.snapshot.devices.length) return;
                    // A >1000-node fixture checks bounded traversal and pagination in the real JS service.
                    const savedSnapshot = Hardware.snapshot;
                    const rawFixture = [];
                    for (let i=0; i<1500; i++) rawFixture.push({id:"/devices/fixture/"+i, parent:"", kernel:"fixture"+i, name:"Node "+i, subsystem:"", category:"Other", kind:"container", virtual:false});
                    Hardware.snapshot = {devices:rawFixture, warnings:[], projection:{entities:[],categories:[],ownerByNode:{},componentCount:0,rawNodeCount:1500}};
                    const firstPage = Hardware.browse("technical", "", "", {}, 60);
                    const lastPage = Hardware.browse("technical", "", "", {}, 600, 1200);
                    test.expect(firstPage.rows.length === 60 && firstPage.total === 1500 && firstPage.more, "Large graph not bounded");
                    test.expect(lastPage.rows.length === 300 && !lastPage.more, "Raw nodes lost at page boundary");
                    test.expect(Hardware.browse("technical", "/devices/fixture/1499", "", {}, 60).rows.length === 1, "Technical search expands ancestors");
                    Hardware.snapshot = savedSnapshot;
                    const devices = Hardware.snapshot.devices;
                    test.expect(find(test.page, "hardware-main-tabs").model.length === 2, "Duplicate driver navigation returned");
                    test.expect(test.page.wide, "Desktop breakpoint incorrect");
                    const nav = find(test.page, "hardware-navigation-pane");
                    const detail = find(test.page, "hardware-detail-pane");
                    test.expect(nav.visible && detail.visible && detail.x > nav.x + nav.width, "Panes are not side by side");
                    test.expect(nav.width / test.page.width > 0.30 && nav.width / test.page.width < 0.40, "Inventory width not balanced");
                    test.expect(test.page.inventory.overview, "Initial view is not category overview");
                    test.expect(test.page.inventory.result.rows.length === 0, "Initial raw universe rendered");
                    click("hardware-row-0");
                    test.expect(test.page.inventory.category !== "", "Category pointer click failed");
                    const initial = Hardware.browse("technical", "", "", {}, 60);
                    test.expect(initial.rows.length <= 60 && initial.rows.every(d => d.depth === 0), "Technical tree starts expanded");
                    const child = devices.find(d => d.subsystem === "hidraw") || devices[0];
                    test.selected = child.id;
                    test.page.select(child.id);
                    test.phase++;
                } else if (test.phase === 2) {
                    if (!Hardware.detail) return;
                    test.expect(Hardware.detail.id === test.selected, "Stale selection");
                    const owner = Hardware.selectedEntity;
                    test.expect(!!owner, "Selected interface lost physical context");
                    const filtered = Hardware.browse("categories", test.selected, "", {}, 60);
                    test.expect(filtered.rows.some(d => d.id === owner.id), "Search lost interface owner");
                    find(test.page, "hardware-search").text = test.selected;
                    test.page.inventory.category = "";
                    test.expect(test.page.inventory.result.rows.some(d => d.id === owner.id), "Search field did not filter physical entities");
                    test.page.inventory.reveal(owner.id);
                    test.expect(test.page.inventory.mode === "topology", "Topology navigation failed");
                    click("hardware-connections-toggle");
                    test.expect(find(test.page, "hardware-connections").expanded, "Interfaces did not open");
                    click("hardware-driver-toggle");
                    test.expect(find(test.page, "hardware-driver").expanded, "Driver detail did not open");
                    find(test.page, "hardware-driver-toggle").forceActiveFocus();
                    pointer.keyClick(Qt.Key_Space);
                    test.expect(!find(test.page, "hardware-driver").expanded, "Keyboard could not close driver details");
                    pointer.keyClick(Qt.Key_Space);
                    test.expect(find(test.page, "hardware-driver").expanded, "Keyboard could not open driver details");
                    test.expect(!find(test.page, "hardware-technical").expanded, "Raw properties open by default");

                    view.width = 460;
                    test.page.showDetail = true;
                    Hardware.validateRule({id:"fixture-qml", label:"QML fixture", subsystem:"hidraw", kernel:"hidraw*", vendor:"abcd", product:"0123", uaccess:true, mode:"", group:"", enabled:true});
                    test.phase++;
                } else if (test.phase === 3) {
                    test.expect(!test.page.wide && !find(test.page, "hardware-navigation-pane").visible, "Narrow layout shows both panes");
                    test.expect(find(test.page, "hardware-detail-pane").width <= test.page.width, "Narrow detail overflows");
                    test.page.tab = 0;
                    click("hardware-narrow-back");
                    test.expect(!test.page.showDetail, "Narrow back navigation failed");
                    click("hardware-advanced-mode");
                    test.expect(test.page.inventory.mode === "technical", "Advanced mode inaccessible");
                    test.expect(test.page.inventory.result.rows.every(d => d.depth === 0), "Advanced mode starts expanded");
                    const branch = test.page.inventory.result.rows.find(d => d.hasChildren);
                    if (branch) {
                        test.page.inventory.toggle(branch.id);
                        test.expect(test.page.inventory.expanded[branch.id], "Branch did not expand");
                    }
                    test.expect(!!Hardware.preview && !Hardware.preview.activeOnHost, "Preview missing or active");
                    test.page.edit(Hardware.preview.rule);
                    Hardware.validateRule(test.page.rule());
                    test.phase++;
                } else if (test.phase === 4) {
                    test.expect(!!Hardware.preview, "Editor roundtrip failed");
                    click("hardware-rule-save");
                    test.phase++;
                } else if (test.phase === 5) {
                    test.expect(Hardware.drafts.length === 1, "Draft save failed");
                    Hardware.setDraftEnabled(Hardware.drafts[0].rule, false);
                    test.phase++;
                } else if (test.phase === 6) {
                    test.expect(!Hardware.drafts[0].rule.enabled, "Draft disable failed");
                    Hardware.removeDraft("fixture-qml");
                    test.phase++;
                } else if (test.phase === 7) {
                    test.expect(Hardware.drafts.length === 0, "Draft delete failed");
                    Hardware.restoreDrafts();
                    test.phase++;
                } else if (test.phase === 8) {
                    test.expect(Hardware.drafts.length === 1, "Draft restore failed");
                    test.page.tab = 0;
                    test.page.select(test.selected);
                    test.phase++;
                } else if (test.phase === 9) {
                    if (!Hardware.detail) return;
                    if (Hardware.detail.ruleSupported) {
                        test.page.prepare();
                        const generated = test.page.rule();
                        test.expect(test.page.tab === 1 && generated.vendor === Hardware.detail.usbSelector.vendor && generated.product === Hardware.detail.usbSelector.product, "Source device selector changed");
                        test.expect(test.page.ruleEditor.sourceId === test.selected, "Source context lost");
                    }
                    view.width = 1250;
                    test.phase++;
                } else if (test.phase === 10) {
                    if (test.page.ruleEditor.sourceId) {
                        click("hardware-return-source");
                        test.expect(test.page.tab === 0 && Hardware.selectedId === test.selected, "Return to source interface failed");
                    }
                    test.phase++;
                } else if (test.phase === 11) {
                    test.page.showDetail = false;
                    test.page.inspector.contentY = 0;
                    test.page.inventory.mode = "categories";
                    test.page.inventory.category = "";
                    if (Quickshell.env("HARDWARE_TEST_SCREENSHOT")) test.page.grabToImage(result => result.saveToFile(Quickshell.env("HARDWARE_TEST_SCREENSHOT")));
                    test.phase++;
                } else if (test.phase === 12) {
                    view.visible = false;
                    test.expect(!Hardware.active, "Hidden window left monitor active");
                    test.page.destroy();
                    test.phase++;
                } else {
                    test.expect(!Hardware.active, "Page left monitor active");
                    console.log("HARDWARE_QML_PASS"); Qt.quit();
                }
            } catch(e) { console.error("HARDWARE_QML_FAIL", String(e)); Qt.quit(); }
        }
    }
    Timer { interval: 18000; running: true; onTriggered: { console.error("HARDWARE_QML_FAIL timeout", Hardware.error); Qt.quit(); } }
}
''')
            (base / "runtime").mkdir(mode=0o700)
            env = dict(os.environ, XDG_RUNTIME_DIR=str(base / "runtime"), QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software",
                       XDG_CONFIG_HOME=str(base / "config"), XDG_STATE_HOME=str(base / "state"),
                       XDG_CACHE_HOME=str(base / "cache"))
            result = subprocess.run([shutil.which("quickshell"), "-p", str(base)], env=env, capture_output=True, text=True, timeout=25)
            logs = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, logs)
            self.assertIn("HARDWARE_QML_PASS", logs)
            for bad in ("HARDWARE_QML_FAIL", "ReferenceError:", "TypeError:", "Cannot assign", "Unable to assign", "Binding loop", "recursive rearrange", "is not a type"):
                self.assertNotIn(bad, logs)
            self.assertFalse(list((base / "state").rglob("*.rules")))

    def test_qt6_syntax(self):
        formatter = Path("/usr/lib/qt6/bin/qmlformat")
        if not formatter.exists(): self.skipTest("Qt6 qmlformat unavailable")
        for name in ("services/Hardware.qml", "modules/settings/HardwareConfig.qml", *["modules/settings/hardware/" + p.name for p in (SOURCE / "modules/settings/hardware").glob("*.qml")]):
            result = subprocess.run([str(formatter), str(SOURCE / name)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__": unittest.main()
