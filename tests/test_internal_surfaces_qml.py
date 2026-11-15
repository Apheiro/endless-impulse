"""Real Settings page/service offscreen, isolated prefs and simulated compositor."""
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

FAKE = '''#!/usr/bin/env python3
import json, os, re, sys
from pathlib import Path
p = Path(os.environ['INTERNAL_TEST_CLIENTS'])
clients = json.loads(p.read_text())
args = sys.argv[1:]
if '-j' in args:
    name = next(a for a in args if a != '-j')
    print(json.dumps({'clients':clients, 'workspaces':[{'id':2,'name':'2'}],
                     'activeworkspace':{'id':2,'name':'2'}, 'monitors':[], 'layers':{}}[name]))
else:
    code = args[-1]
    if 'hl.dsp.window.move' in code:
        target, address = re.search(r'workspace="([^"]+)".*address:(0x[0-9a-f]+)', code).groups()
        for client in clients:
            if client['address'] == address:
                client['workspace'] = {'id':-99 if target.startswith('special:') else int(target),'name':target}
        p.write_text(json.dumps(clients))
    print('ok')
'''


class InternalSurfacesQmlTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("quickshell"), "Quickshell is needed for the offscreen integration")
    def test_real_page_validation_persistence_filters_and_restore(self):
        with tempfile.TemporaryDirectory(prefix="endless-internal-qml-") as temporary:
            base = Path(temporary)
            for name in ("scripts", "assets", "defaults", "translations"):
                (base / name).symlink_to(SOURCE / name)
            def write(name, text):
                path = base / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            def copy(name):
                write(name, (SOURCE / name).read_text())
            for name in ("InternalSurfaces", "HyprlandData"):
                copy("services/" + name + ".qml")
            shutil.copytree(SOURCE / "services/hyprland", base / "services/hyprland")
            for name in ("InternalSurfacesConfig", "SettingsPage", "SettingsSection"):
                copy("modules/settings/" + name + ".qml")
            for name in ("SettingsCard", "ContentPage"):
                copy("modules/shared/primitives/settings/" + name + ".qml")
            for name in ("StyledText", "MaterialSymbol", "MaterialTextField", "RippleButton", "StyledFlickable", "StyledScrollBar"):
                copy("modules/shared/primitives/common/" + name + ".qml")
            copy("modules/shared/widgets/RippleButtonWithIcon.qml")
            copy("modules/shared/Config.qml")
            copy("modules/shared/functions/ColorUtils.qml")
            write("services/Translation.qml", 'pragma Singleton\nimport QtQuick\nQtObject { function tr(text) { return text; } }')
            write("modules/shared/Directories.qml", 'pragma Singleton\nimport QtQuick\nimport Quickshell\nQtObject { property string shellConfigPath: Quickshell.shellPath("config/endless-Impulse/config.json"); property string videos: "file:///tmp" }')
            appearance = (SOURCE / "modules/shared/Appearance.qml").read_text()
            colors = {key: "#eeeeee" if key.startswith("colOn") else "#333333" for key in re.findall(r"property color (col\w+):", appearance)}
            m3 = dict(re.findall(r'property color (m3\w+): "(#[^"]+)"', appearance), darkmode=True)
            tokens = dict(colors=colors, m3colors=m3,
                          font=dict(family=dict(main="Sans", numbers="Sans", iconMaterial="Sans", iconNerd="Sans"), pixelSize=dict(small=14, smaller=12, normal=15, larger=18), variableAxes=dict(main={})),
                          rounding=dict(small=8, normal=12, large=16, unsharpenmore=8),
                          sizes=dict(textInputHorizontalPadding=12, textInputVerticalPadding=8, textInputMinimumHeight=40),
                          animationCurves=dict(standardDecel=[0,0,1,1,1,1]))
            animation = '''property QtObject animation: QtObject {
                property QtObject elementMoveFast: QtObject { id: fast; property int duration: 0; property int type: Easing.Linear; property var bezierCurve: [0,0,1,1,1,1]; property Component colorAnimation: ColorAnimation { duration: 0 } }
                property QtObject elementMoveEnter: fast
                property QtObject scroll: fast
            }'''
            write("modules/shared/Appearance.qml", 'pragma Singleton\nimport QtQuick\nQtObject {\n'
                  + ''.join('property var ' + key + ':' + json.dumps(value) + '\n' for key, value in tokens.items())
                  + animation + '\nfunction animationDuration(ms) { return 0; } }')
            (base / "config/endless-Impulse").mkdir(parents=True)
            (base / "config/endless-Impulse/config.json").write_text('{}')
            (base / "bin").mkdir()
            fake = base / "bin/hyprctl"
            fake.write_text(FAKE)
            fake.chmod(0o755)
            clients = [dict(address="0x1", pid=42, stableId="1", initialTitle="", title="",
                            **{"class":"xembedsniproxy"}, mapped=True, floating=True, xwayland=True,
                            workspace=dict(id=2, name="2"))]
            (base / "clients.json").write_text(json.dumps(clients))
            (base / "shell.qml").write_text('''//@ pragma UseQApplication
//@ pragma Env QT_QUICK_CONTROLS_STYLE=Basic
import QtQuick
import Quickshell
import qs.modules.settings
import qs.services
import qs.modules.shared
ShellRoot {
    id: root
    property int phase: 0
    property var page: null
    property Component pageType: InternalSurfacesConfig { width: 800; height: 600 }
    function expect(condition, message) { if (!condition) throw new Error(message); }
    function find(item, name) {
        if (item.objectName === name) return item;
        for (const child of item.children || []) { const found = find(child, name); if (found) return found; }
        return null;
    }
    function add(cls, title, purpose) {
        find(page, "internal-surface-class").text = cls;
        find(page, "internal-surface-title").text = title;
        find(page, "internal-surface-purpose").text = purpose;
        find(page, "internal-surface-add").click();
    }
    Timer {
        interval: 250; running: true; repeat: true
        onTriggered: {
            try {
                if (!Config.ready || InternalSurfaces.busy) return;
                if (root.phase === 0) {
                    root.page = root.pageType.createObject(root);
                    root.expect(root.page !== null, "Settings page did not load");
                } else if (root.phase === 1) {
                    root.expect(!InternalSurfaces.error, InternalSurfaces.error);
                    root.expect(InternalSurfaces.entries.length === 1, "Missing builtin");
                    root.expect(HyprlandData.windowList[0].workspace.name === InternalSurfaces.workspace, "Container not moved");
                    root.expect(InternalSurfaces.isInternal({appId:"xembedsniproxy",HyprlandToplevel:{address:"1"}}), "Internal filter missed the proxy");
                    root.expect(!InternalSurfaces.isInternal({appId:"editor",HyprlandToplevel:{address:"2"}}), "Ordinary window filtered");
                    root.add("quickshell", "Settings", "Do not allow this");
                } else if (root.phase === 2) {
                    root.expect(InternalSurfaces.error !== "", "Critical class accepted");
                    root.expect(Config.options.internalSurfaces.rules.length === 0, "Invalid rule saved");
                    root.add("aux-tray", "Capture holder", "Legacy capture");
                } else if (root.phase === 3) {
                    root.expect(!InternalSurfaces.error, InternalSurfaces.error);
                    root.expect(Config.options.internalSurfaces.rules.length === 1, "Manual rule not saved");
                    root.expect(InternalSurfaces.entries.length === 2, "Manual inventory missing");
                    InternalSurfaces.setEnabled(InternalSurfaces.entries[0], false);
                } else if (root.phase === 4) {
                    root.expect(!Config.options.internalSurfaces.xembedEnabled, "Builtin still enabled");
                    root.expect(HyprlandData.windowList[0].workspace.name === "2", "Container not restored");
                    root.expect(!InternalSurfaces.isInternal({appId:"xembedsniproxy",HyprlandToplevel:{address:"1"}}), "Disabled proxy still filtered");
                    InternalSurfaces.remove(InternalSurfaces.entries[1]);
                } else {
                    root.expect(Config.options.internalSurfaces.rules.length === 0, "Manual rule not removed");
                    root.expect(!InternalSurfaces.error, InternalSurfaces.error);
                    console.log("INTERNAL_SURFACES_QML_OK"); Qt.quit(); return;
                }
                root.phase++;
            } catch (error) { console.error("INTERNAL_SURFACES_QML_FAILED", error); Qt.quit(); }
        }
    }
    Timer { interval: 12000; running: true; onTriggered: {console.error("INTERNAL_SURFACES_QML_FAILED timeout"); Qt.quit();} }
}
''')
            env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", QT_QPA_PLATFORMTHEME="",
                       XDG_CONFIG_HOME=str(base / "config"), XDG_STATE_HOME=str(base / "state"),
                       XDG_CACHE_HOME=str(base / "cache"), XDG_RUNTIME_DIR=str(base / "runtime"),
                       HYPRLAND_INSTANCE_SIGNATURE="internal-test", DOTS_SHELL_SOURCE=str(base),
                       INTERNAL_TEST_CLIENTS=str(base / "clients.json"), PATH=str(base / "bin") + ":" + os.environ["PATH"])
            (base / "runtime").mkdir(mode=0o700)
            result = subprocess.run([shutil.which("quickshell"), "-p", str(base)], env=env,
                                    capture_output=True, text=True, timeout=15)
            logs = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, logs)
            self.assertIn("INTERNAL_SURFACES_QML_OK", logs)
            for error in ("INTERNAL_SURFACES_QML_FAILED", "ReferenceError", "TypeError", "Cannot assign", "Binding loop", "Unable to assign"):
                self.assertNotIn(error, logs)
            saved = json.loads((base / "config/endless-Impulse/config.json").read_text())["internalSurfaces"]
            self.assertEqual(saved, dict(xembedEnabled=False, rules=[]))


if __name__ == "__main__":
    unittest.main()
