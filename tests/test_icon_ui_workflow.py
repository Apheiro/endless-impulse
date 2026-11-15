"""Exercise asynchronous icon settings and cross-instance file watching."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "src/quickshell"


@unittest.skipUnless(os.environ.get("WAYLAND_DISPLAY"), "Quickshell needs Wayland")
class IconWorkflowTests(unittest.TestCase):
    def test_preview_apply_override_reset_and_live_resolution(self):
        with tempfile.TemporaryDirectory(prefix="dots-icon-ui-") as temporary:
            base = Path(temporary)
            for name in ("modules", "services", "assets", "scripts", "defaults", "translations", "GlobalStates.qml", "welcome.qml"):
                (base / name).symlink_to(SOURCE / name, target_is_directory=(SOURCE / name).is_dir())
            icons = base / "data/icons/Base"
            (icons / "48x48/apps").mkdir(parents=True)
            (icons / "index.theme").write_text("[Icon Theme]\nName=Base\nDirectories=48x48/apps\n[48x48/apps]\nSize=48\nType=Fixed\n")
            (icons / "48x48/apps/folder.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48"><rect width="48" height="48" fill="blue"/></svg>')
            other = base / "data/icons/Other"
            (other / "48x48/apps").mkdir(parents=True)
            (other / "index.theme").write_text((icons / "index.theme").read_text().replace("Name=Base", "Name=Other"))
            (other / "48x48/apps/folder.svg").write_text((icons / "48x48/apps/folder.svg").read_text().replace("blue", "red"))
            third = base / "data/icons/Third"
            (third / "48x48/apps").mkdir(parents=True)
            (third / "index.theme").write_text((icons / "index.theme").read_text().replace("Name=Base", "Name=Third"))
            appdir = base / "data/applications"
            appdir.mkdir(parents=True)
            (appdir / "demo.desktop").write_text("[Desktop Entry]\nName=Demo\nType=Application\nIcon=folder\nExec=true\n")
            config = base / "config"
            config.mkdir()
            (config / "kdeglobals").write_text("[Icons]\nTheme=Base\n")
            fixture = '''import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import qs.modules.settings
import qs.services
ShellRoot {
    property int phase: 0
    property int ticks: 0
    PanelWindow {
        implicitWidth:960;implicitHeight:850;exclusiveZone:0
        WlrLayershell.namespace:"quickshell:icon-fallback-test"
        WlrLayershell.keyboardFocus:WlrKeyboardFocus.None
        mask:Region{}
        IconsConfig{id:page;anchors.fill:parent}
    }
    Process {
        id: externalWriter
        command: ["python3", Quickshell.shellPath("scripts/icons/themes.py"), "apply"]
        stdinEnabled: true
        onStarted: { write(JSON.stringify({theme: "Other"})); stdinEnabled = false; }
        stdout: StdioCollector {}
        stderr: StdioCollector {}
    }
    Timer {
        interval: 100; running: true; repeat: true
        onTriggered: {
            if (++parent.ticks > 180) { console.error("ICON_WORKFLOW_TIMEOUT", parent.phase, IconTheme.message, JSON.stringify(IconTheme.paths.filter(path=>!path.exists))); Qt.quit(); return; }
            if (!IconTheme.loaded || IconTheme.busy) return;
            if (IconTheme.failed) { console.error("ICON_WORKFLOW_FAILED", IconTheme.message); Qt.quit(); return; }
            switch (parent.phase) {
            case 0:
                page.selectedTheme="Base";
                page.addFallback("Other");page.addFallback("Third");page.moveFallback(1,-1);
                if (JSON.stringify(page.selectedFallbacks)!==JSON.stringify(["Third","Other"])) {console.error("ICON_BACKUP_ORDER_FAILED");Qt.quit();return;}
                page.selectedFallbacks=page.selectedFallbacks.filter(theme=>theme!=="Third");
                IconTheme.preview("Base", page.selectedFallbacks); parent.phase++; break;
            case 1:
                if (IconTheme.previewTheme !== "Base" || !IconTheme.previewIcons.folder) return;
                IconTheme.preview("Base", ["Other"]);
                IconTheme.apply({theme: "Base", fallbacks: ["Other"]}); parent.phase++; break;
            case 2:
                if (IconTheme.paths.some(p => !p.exists)) return;
                if (JSON.stringify(IconTheme.fallbacks)!==JSON.stringify(["Other"])) {console.error("ICON_FALLBACKS_NOT_APPLIED");Qt.quit();return;}
                IconTheme.apply({theme: "Base", application: "demo.desktop", source: "folder"}); parent.phase++; break;
            case 3:
                if (!IconTheme.overrides["demo.desktop"]) return;
                if (!IconTheme.aliases.demo?.includes("EndlessImpulse")) { console.error("ICON_OVERRIDE_NOT_LIVE"); Qt.quit(); return; }
                IconTheme.apply({theme: "Base", application: "demo.desktop", reset: true}); parent.phase++; break;
            case 4:
                if (IconTheme.overrides["demo.desktop"]) return;
                if (!IconTheme.iconPath("folder").includes("/Base/")) { console.error("ICON_DEFAULT_NOT_RESTORED"); Qt.quit(); return; }
                externalWriter.running = true; parent.phase++; break;
            case 5:
                if (IconTheme.theme !== "Other") return;
                if (!IconTheme.iconPath("folder").includes("/Other/")) { console.error("ICON_EXTERNAL_CHANGE_NOT_LIVE"); Qt.quit(); return; }
                console.log("ICON_WORKFLOW_OK"); Qt.quit();
            }
        }
    }
}'''
            (base / "shell.qml").write_text(fixture)
            environment = dict(os.environ, DOTS_SHELL_SOURCE=str(base), HOME=str(base),
                               XDG_CONFIG_HOME=str(config), XDG_DATA_HOME=str(base / "data"),
                               XDG_STATE_HOME=str(base / "state"), XDG_CACHE_HOME=str(base / "cache"),
                               XDG_DATA_DIRS=str(base / "share"), GSETTINGS_BACKEND="memory")
            launcher = environment.get("DOTS_TEST_LAUNCHER")
            command = [launcher] if launcher else [shutil.which("quickshell"), "-p", str(base / "shell.qml")]
            result = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=25)
            logs = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, logs)
            self.assertIn("ICON_WORKFLOW_OK", logs)
            self.assertNotIn("ReferenceError:", logs)
            self.assertNotIn("TypeError:", logs)
            self.assertIn("Theme=EndlessImpulse", (config / "kdeglobals").read_text())
            self.assertIn("gtk-icon-theme-name=EndlessImpulse", (config / "gtk-4.0/settings.ini").read_text())
