"""Load every settings page and exercise category discovery without user config."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "dots/.config/quickshell/ii"


@unittest.skipUnless(os.environ.get("WAYLAND_DISPLAY"), "Quickshell needs a Wayland connection")
class SettingsNavigationTests(unittest.TestCase):
    def test_all_pages_and_filtered_navigation(self):
        with tempfile.TemporaryDirectory(prefix="dots-settings-test-") as temporary:
            base = Path(temporary)
            for name in ("modules", "services", "assets", "scripts", "defaults", "translations", "GlobalStates.qml", "welcome.qml"):
                (base / name).symlink_to(SOURCE / name, target_is_directory=(SOURCE / name).is_dir())
            text = (SOURCE / "settings.qml").read_text().replace("    property bool allowShowing: true", "    property bool allowShowing: false", 1)
            text = text.rstrip()[:-1] + '''
    Timer {
        interval: 80
        running: true
        onTriggered: {
            HyprlandData.monitors = Quickshell.screens.map((screen, index) => ({
                name: screen.name, focused: index === Quickshell.screens.length - 1,
                reserved: [0,45,0,0]
            }));
        }
    }
    Timer {
        interval: 120
        running: true
        repeat: true
        property int visited: 0
        onTriggered: {
            if (!Config.ready) return;
            if (pageLoader.status !== Loader.Ready || !pageLoader.item) {
                console.error("SETTINGS_FAILED", root.selectedPage.component, pageLoader.status);
                Qt.quit();
                return;
            }
            console.log("SETTINGS_PAGE_OK", root.selectedPage.component);
            visited++;
            if (visited < root.pages.length) {
                root.currentPage = visited;
                return;
            }
            const checks = [
                ["tipografía", "FontsConfig.qml"], ["búsqueda", "OverviewConfig.qml"],
                ["captura", "CaptureConfig.qml"], ["batería", "SystemConfig.qml"],
                ["tray icons", "BarConfig.qml"], ["privacidad", "SecurityConfig.qml"]
            ];
            for (const [query, expected] of checks) {
                navigationSearch.text = query;
                const match = root.pages.findIndex((page, index) => catalog.matches(index, query));
                if (match < 0 || root.pages[match].component !== expected) {
                    console.error("SETTINGS_SEARCH_FAILED", query);
                    Qt.quit(); return;
                }
            }
            navigationSearch.text = "no-such-category-xyz";
            const before = root.currentPage;
            root.movePage(1);
            if (root.matchingPages !== 0 || root.currentPage !== before) {
                console.error("SETTINGS_EMPTY_SEARCH_FAILED"); Qt.quit(); return;
            }
            navigationSearch.clear();
            root.currentPage = root.pages.length - 1;
            root.movePage(1);
            if (root.currentPage !== 0) { console.error("SETTINGS_WRAP_FAILED"); Qt.quit(); return; }
            root.movePage(-1);
            if (root.currentPage !== root.pages.length - 1) { console.error("SETTINGS_WRAP_FAILED"); Qt.quit(); return; }
            if (!root.opened || root.openingMonitorName !== Quickshell.screens[Quickshell.screens.length - 1].name) {
                console.error("SETTINGS_OPENING_SCREEN_FAILED", root.openingMonitorName); Qt.quit(); return;
            }
            const initialWidth = root.implicitWidth;
            const initialHeight = root.implicitHeight;
            for (const [w, h, reserved, expectedW, expectedH] of [
                [1440,2560,[0,45,0,0],1152,2012],
                [2560,1440,[0,45,0,0],2048,1116],
                [1920,1080,[0,40,0,0],1536,832]]) {
                const size = root.sizeForScreen(w, h, reserved);
                if (size.width !== expectedW || size.height !== expectedH) {
                    console.error("SETTINGS_MONITOR_FAILED", size); Qt.quit(); return;
                }
            }
            HyprlandData.monitors = [{name: root.openingMonitorName, reserved: [200,200,200,200]}];
            root.finishOpening();
            if (root.implicitWidth !== initialWidth || root.implicitHeight !== initialHeight) {
                console.error("SETTINGS_SIZE_CHANGED_AFTER_OPEN"); Qt.quit(); return;
            }
            const welcome = Qt.createComponent(Qt.resolvedUrl("welcome.qml"));
            if (welcome.status !== Component.Ready) {
                console.error("WELCOME_FAILED", welcome.errorString()); Qt.quit(); return;
            }
            console.log("SETTINGS_MONITOR_OK");
            console.log("SETTINGS_NAVIGATION_OK", visited);
            Qt.quit();
        }
    }
}
'''
            (base / "settings.qml").write_text(text)
            environment = dict(os.environ, DOTS_SHELL_SOURCE=str(base),
                               HYPRLAND_INSTANCE_SIGNATURE="isolated-settings-test",
                               XDG_CONFIG_HOME=str(base / "config"), XDG_STATE_HOME=str(base / "state"),
                               XDG_CACHE_HOME=str(base / "cache"))
            launcher = environment.get("DOTS_TEST_LAUNCHER")
            command = [str(Path(launcher).with_name("dots-hyperland-settings"))] if launcher else [shutil.which("quickshell"), "-p", str(base / "settings.qml")]
            result = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=20)
            logs = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, logs)
            self.assertIn("SETTINGS_NAVIGATION_OK 13", logs)
            self.assertIn("SETTINGS_MONITOR_OK", logs)
            self.assertNotIn("SETTINGS_FAILED", logs)
            self.assertNotIn("ReferenceError:", logs)
            self.assertNotIn("TypeError:", logs)
