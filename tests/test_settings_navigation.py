"""Load every settings page and exercise category discovery without user config."""
import os
import importlib.util
import json
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
            spec = importlib.util.spec_from_file_location("desktop_schema", SOURCE / "scripts/hyprland/desktop.py")
            schema = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(schema)
            catalog = base / "state/artificial-impulse/shortcuts-catalog.json"
            catalog.parent.mkdir(parents=True)
            catalog.write_text(json.dumps([
                {"id": "|SUPER+TAB", "default": "SUPER + Tab", "submap": "", "description": "Shell: Overview", "category": "Shell", "count": 1},
                {"id": "|CTRL+SUPER+F1", "default": "CTRL + SUPER + F1", "submap": "", "description": "Window: Focus", "category": "Window", "count": 2}
            ]))
            text = (SOURCE / "settings.qml").read_text().replace("    property bool allowShowing: true", "    property bool allowShowing: false", 1)
            text = text.replace("WlrKeyboardFocus.OnDemand", "WlrKeyboardFocus.None").replace("quickshell:settings", "quickshell:settings-test")
            text = text.rstrip()[:-1] + '''
    Timer {
        interval: 80
        running: true
        onTriggered: {
            DesktopSettings.fields = __DESKTOP_FIELDS__;
            DesktopSettings.values = __DESKTOP_VALUES__;
            const supported = {};
            for (const field of DesktopSettings.fields) supported[field.key] = true;
            DesktopSettings.supported = supported;
            DesktopSettings.monitors = [
                {name: "TEST-1", description: "Main", availableModes: ["2560x1440@165.00Hz"], current: {mode: "2560x1440@165.00Hz", x: 0, y: 0, scale: 1, transform: 0}},
                {name: "TEST-2", description: "Portrait", availableModes: ["1920x1080@60.00Hz"], current: {mode: "1920x1080@60.00Hz", x: 2560, y: 0, scale: 1, transform: 1}}
            ];
            DesktopSettings.devices = [{name: "fixture-keyboard", kind: "keyboards"}, {name: "fixture-mouse", kind: "mice"}];
            DesktopSettings.loaded = true;
            DesktopSettings.integrated = true;
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
        property bool checkedShortcutEditor: false
        property int mapPhase: 0
        property real expandedMapHeight: 0
        property int shortcutPhase: 0
        property real compactShortcutHeight: 0
        onTriggered: {
            if (!Config.ready) return;
            if (pageLoader.status !== Loader.Ready || !pageLoader.item) {
                console.error("SETTINGS_FAILED", root.selectedPage.component, pageLoader.status);
                Qt.quit();
                return;
            }
            if (pageLoader.item.environmentPaths && !pageLoader.item.environmentPaths.expanded) {
                pageLoader.item.environmentPaths.expanded = true;
                return;
            }
            if (root.selectedPage.component === "ShortcutsConfig.qml" && !checkedShortcutEditor) {
                if (!pageLoader.item.shortcuts.length) return;
                if (shortcutPhase === 0) {
                    // Layout geometry needs a rendered frame. Briefly map this isolated,
                    // keyboard-unfocusable fixture only for the accordion size checks.
                    root.allowShowing = true;
                    shortcutPhase++;
                    return;
                }
                if (shortcutPhase === 1) {
                    compactShortcutHeight = pageLoader.item.contentHeight;
                    pageLoader.item.expandedCategories = {Shell: true, Window: true};
                    pageLoader.item.select(pageLoader.item.shortcuts[0]);
                    shortcutPhase++;
                    return;
                }
                if (shortcutPhase === 2) {
                    if (pageLoader.item.contentHeight <= compactShortcutHeight + 50) {
                        console.error("SHORTCUT_EXPANSION_FAILED", compactShortcutHeight, pageLoader.item.contentHeight); Qt.quit(); return;
                    }
                    pageLoader.item.expandedCategories = {};
                    pageLoader.item.selectedId = "";
                    shortcutPhase++;
                    return;
                }
                if (shortcutPhase === 3) {
                    if (pageLoader.item.contentHeight > compactShortcutHeight + 1) {
                        console.error("SHORTCUT_COLLAPSE_HEIGHT_FAILED", compactShortcutHeight, pageLoader.item.contentHeight); Qt.quit(); return;
                    }
                    pageLoader.item.expandedCategories = {Shell: true, Window: true};
                    pageLoader.item.showGuide = true;
                    pageLoader.item.select(pageLoader.item.shortcuts[0]);
                    shortcutPhase++;
                    return;
                }
                root.allowShowing = false;
                checkedShortcutEditor = true;
            }
            if (root.selectedPage.component === "About.qml" && mapPhase < 4) {
                const map = pageLoader.item.installationMap;
                if (!InstallationPaths.loaded || InstallationPaths.busy) return;
                if (InstallationPaths.error || map.pathCount < 30) {
                    console.error("PATH_MAP_LOAD_FAILED", InstallationPaths.error, map.pathCount); Qt.quit(); return;
                }
                if (mapPhase === 0) {
                    root.allowShowing = true;
                    const all = {};
                    function expand(nodes) { for (const node of nodes) { all[node.id] = true; expand(node.children); } }
                    expand(InstallationPaths.groups);
                    map.expanded = all;
                } else if (mapPhase === 1) {
                    expandedMapHeight = map.implicitHeight;
                    const screenshot = Quickshell.env("DOTS_TEST_MAP_SCREENSHOT");
                    if (screenshot) pageLoader.item.grabToImage(result => { result.saveToFile(screenshot); map.expanded = {}; });
                    else map.expanded = {};
                } else if (mapPhase === 2) {
                    if (map.implicitHeight >= expandedMapHeight - 100 || map.rows.length !== 3) {
                        console.error("PATH_MAP_COLLAPSE_FAILED", map.implicitHeight, expandedMapHeight); Qt.quit(); return;
                    }
                    map.query = "hyprland";
                } else {
                    if (!map.rows.some(row => row.node.path.includes("hypr")) || map.rows.length < 3) {
                        console.error("PATH_MAP_SEARCH_FAILED"); Qt.quit(); return;
                    }
                    root.allowShowing = false;
                    console.log("PATH_MAP_OK", map.pathCount);
                }
                mapPhase++;
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
                ["tray icons", "BarConfig.qml"], ["privacidad", "SecurityConfig.qml"],
                ["monitores", "MonitorsConfig.qml"], ["desenfoque", "HyprlandConfig.qml"], ["sensibilidad", "InputConfig.qml"]
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
            if (DesktopSettings.changes !== 0) {
                console.error("DESKTOP_SETTINGS_CHANGED_ON_OPEN"); Qt.quit(); return;
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
            text = text.replace("__DESKTOP_FIELDS__", json.dumps(schema.FIELDS)).replace("__DESKTOP_VALUES__", json.dumps({field["key"]: field["default"] for field in schema.FIELDS}))
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
            self.assertIn("SETTINGS_NAVIGATION_OK 17", logs)
            self.assertIn("SETTINGS_MONITOR_OK", logs)
            self.assertIn("PATH_MAP_OK", logs)
            self.assertNotIn("SETTINGS_FAILED", logs)
            self.assertNotIn("ReferenceError:", logs)
            self.assertNotIn("TypeError:", logs)
