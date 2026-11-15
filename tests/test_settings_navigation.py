"""Load every settings page and exercise category discovery without user config."""
import os
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/quickshell"


@unittest.skipUnless(os.environ.get("WAYLAND_DISPLAY"), "Quickshell needs a Wayland connection")
class SettingsNavigationTests(unittest.TestCase):
    def test_outside_click_dismissal(self):
        with tempfile.TemporaryDirectory(prefix="dots-settings-dismiss-") as temporary:
            base = Path(temporary)
            for name in ("modules", "services", "assets", "scripts", "defaults", "translations", "GlobalStates.qml"):
                (base / name).symlink_to(SOURCE / name)
            text = (SOURCE / "settings.qml").read_text().replace("property bool allowShowing: true", "property bool allowShowing: false")
            text = text.rstrip()[:-1] + '''
    Timer {
        interval: 300; running: true
        onTriggered: {
            if (settingsFocusGrab.active || settingsFocusGrab.windows.length !== 1 || settingsFocusGrab.windows[0] !== root) {
                console.error("SETTINGS_DISMISS_FAILED"); Qt.quit(); return;
            }
            console.log("SETTINGS_OUTSIDE_CLICK");
            settingsFocusGrab.cleared();
            console.log("SETTINGS_DISMISS_REQUESTED");
        }
    }
    Timer { interval: 2000; running: true; onTriggered: { console.error("SETTINGS_DISMISS_FAILED timeout"); Qt.quit(); } }
}
'''
            (base / "shell.qml").write_text(text)
            env = dict(os.environ, DOTS_SHELL_SOURCE=str(base), XDG_CONFIG_HOME=str(base / "config"),
                       XDG_STATE_HOME=str(base / "state"), XDG_CACHE_HOME=str(base / "cache"))
            launcher = env.get("DOTS_TEST_LAUNCHER")
            result = subprocess.run([launcher] if launcher else [shutil.which("quickshell"), "-p", str(base)],
                                    env=env, capture_output=True, text=True, timeout=8)
            logs = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, logs)
            self.assertIn("SETTINGS_DISMISS_REQUESTED", logs)
            for error in ("SETTINGS_DISMISS_FAILED", "TypeError:", "ReferenceError:", "Cannot assign", "Unable to assign"):
                self.assertNotIn(error, logs)

    def test_all_pages_and_filtered_navigation(self):
        expected_page_count = (SOURCE / "modules/settings/SettingsCatalog.qml").read_text().count('component: "')
        with tempfile.TemporaryDirectory(prefix="dots-settings-test-") as temporary:
            base = Path(temporary)
            for name in ("modules", "services", "assets", "scripts", "defaults", "translations", "GlobalStates.qml", "welcome.qml"):
                if name == "services":
                    shutil.copytree(SOURCE / name, base / name)
                    # This broad navigation smoke test must never analyze real
                    # user directories when visiting the Storage page.
                    storage_service = base / "services/Storage.qml"
                    storage_service.write_text(storage_service.read_text().replace(
                        "function activateSelection() {", "function activateSelection() { return;", 1).replace(
                        'function analyze(path = "") {', 'function analyze(path = "") { return;', 1))
                else:
                    (base / name).symlink_to(SOURCE / name, target_is_directory=(SOURCE / name).is_dir())
            spec = importlib.util.spec_from_file_location("desktop_schema", SOURCE / "scripts/hyprland/desktop.py")
            schema = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(schema)
            catalog = base / "state/endless-Impulse/shortcuts-catalog.json"
            catalog.parent.mkdir(parents=True)
            catalog.write_text(json.dumps([
                {"id": "|SUPER+TAB", "default": "SUPER + Tab", "submap": "", "description": "Shell: Overview", "category": "Shell", "count": 1},
                {"id": "|CTRL+SUPER+F1", "default": "CTRL + SUPER + F1", "submap": "", "description": "Window: Focus", "category": "Window", "count": 2}
            ]))
            text = (SOURCE / "settings.qml").read_text().replace("    property bool allowShowing: true", "    property bool allowShowing: false", 1)
            text = text.replace("shown: root.visible", "shown: false")
            text = text.replace("WlrKeyboardFocus.OnDemand", "WlrKeyboardFocus.None").replace("quickshell:settings", "quickshell:settings-test")
            text = text.rstrip()[:-1] + '''
    Timer {
        interval: 80
        running: true
        onTriggered: {
            if (root.selectedPage.component !== "AudioConfig.qml" || AudioControl.section !== "profiles") { console.error("SETTINGS_DEEP_LINK_FAILED"); Qt.quit(); return; }
            root.selectSection("network/wifi");
            if (root.selectedPage.component !== "NetworkConfig.qml" || NetworkControl.page !== "wifi") { console.error("SETTINGS_DEEP_LINK_FAILED"); Qt.quit(); return; }
            root.selectSection("firewall");
            if (root.selectedPage.component !== "FirewallConfig.qml") { console.error("SETTINGS_DEEP_LINK_FAILED firewall"); Qt.quit(); return; }
            root.selectSection("security-network");
            if (root.selectedPage.component !== "FirewallConfig.qml" || root.pages.length !== __SETTINGS_PAGE_COUNT__) { console.error("SETTINGS_DEEP_LINK_FAILED security-network"); Qt.quit(); return; }
            root.currentPage = 0;
            console.log("SETTINGS_DEEP_LINK_OK");
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
        property bool checkedRecording: false
        property int dependencyPhase: 0
        property real dependencyHeight: 0
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
            if (root.selectedPage.component === "RecordingConfig.qml" && !checkedRecording) {
                if (!ScreenRecorder.loaded || ScreenRecorder.busy) return;
                // The recorder now has separate tabs; FPS lives under Video.
                pageLoader.item.currentTab = 1;
                function findEditor(item) {
                    if (item.objectName === "recorder-value-fps") return item;
                    for (const child of item.children || []) { const found = findEditor(child); if (found) return found; }
                    return null;
                }
                const fpsEditor = findEditor(pageLoader.item);
                if (!fpsEditor) return;
                fpsEditor.value = 144;
                fpsEditor.valueModified();
                if (pageLoader.item.draft.fps !== 144 || !pageLoader.item.dirty) {
                    console.error("RECORDER_EDIT_FAILED"); Qt.quit(); return;
                }
                pageLoader.item.reset();
                checkedRecording = true;
                return;
            }
            if (root.selectedPage.component === "About.qml" && dependencyPhase < 4) {
                const map = pageLoader.item.dependencyMap;
                if (DependencyInfo.busy || !DependencyInfo.groups.length) return;
                if (DependencyInfo.error || DependencyInfo.catalog.total < 40) { console.error("DEPENDENCY_MAP_FAILED"); Qt.quit(); return; }
                if (dependencyPhase === 0) {
                    root.allowShowing = true;
                    const distroY = pageLoader.item.distroSection.mapToItem(pageLoader.item, 0, 0).y;
                    if (distroY >= map.mapToItem(pageLoader.item, 0, 0).y) { console.error("ABOUT_DISTRO_ORDER_FAILED"); Qt.quit(); return; }
                    map.toggle("group:runtime");
                } else if (dependencyPhase === 1) {
                    if (!map.rows.some(row => row.node.package === "quickshell")) { console.error("DEPENDENCY_MAP_EXPAND_FAILED"); Qt.quit(); return; }
                    dependencyHeight = map.implicitHeight;
                    map.expanded = {};
                } else if (dependencyPhase === 2) {
                    if (map.implicitHeight >= dependencyHeight || map.rows.length !== DependencyInfo.groups.length) { console.error("DEPENDENCY_MAP_COLLAPSE_FAILED"); Qt.quit(); return; }
                    map.query = "wireplumber";
                } else {
                    if (!map.rows.some(row => row.node.package === "wireplumber")) { console.error("DEPENDENCY_MAP_SEARCH_FAILED"); Qt.quit(); return; }
                    if (DependencyInfo.groups.some(group => group.children.some(node => node.retired || node.id.startsWith("legacy:") || node.id.startsWith("replaced:")))) { console.error("DEPENDENCY_MAP_RETIRED_FAILED"); Qt.quit(); return; }
                    map.query = "";
                    map.showSources = true;
                    console.log("DEPENDENCY_MAP_OK", DependencyInfo.catalog.total);
                }
                dependencyPhase++;
                return;
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
            if (["MonitorsConfig.qml", "HyprlandConfig.qml", "InputConfig.qml"].includes(root.selectedPage.component)) {
                if (!desktopActions.active || !desktopActions.item || desktopActions.parent === pageLoader.item) {
                    console.error("DESKTOP_ACTIONS_NOT_PINNED"); Qt.quit(); return;
                }
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
                ["cortafuegos", "FirewallConfig.qml"], ["firewalld", "FirewallConfig.qml"],
                ["almacenamiento", "StorageConfig.qml"],
                ["monitores", "MonitorsConfig.qml"], ["desenfoque", "HyprlandConfig.qml"], ["sensibilidad", "InputConfig.qml"]
            ];
            for (const [query, expected] of checks) {
                navigationSearch.text = query;
                // A query can legitimately match multiple sections (e.g. blur and Xray).
                const match = root.pages.findIndex((page, index) => page.component === expected && catalog.matches(index, query));
                if (match < 0) {
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
            text = text.replace("__SETTINGS_PAGE_COUNT__", str(expected_page_count))
            (base / "settings.qml").write_text(text)
            environment = dict(os.environ, DOTS_SHELL_SOURCE=str(base), DOTS_SETTINGS_PAGE="audio/profiles",
                               HYPRLAND_INSTANCE_SIGNATURE="isolated-settings-test",
                               XDG_CONFIG_HOME=str(base / "config"), XDG_STATE_HOME=str(base / "state"),
                               XDG_CACHE_HOME=str(base / "cache"))
            launcher = environment.get("DOTS_TEST_LAUNCHER")
            command = [str(Path(launcher).with_name("dots-hyperland-settings"))] if launcher else [shutil.which("quickshell"), "-p", str(base / "settings.qml")]
            result = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=20)
            logs = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, logs)
            self.assertIn(f"SETTINGS_NAVIGATION_OK {expected_page_count}", logs)
            self.assertIn("SETTINGS_MONITOR_OK", logs)
            self.assertIn("SETTINGS_DEEP_LINK_OK", logs)
            self.assertIn("PATH_MAP_OK", logs)
            self.assertIn("DEPENDENCY_MAP_OK", logs)
            self.assertNotIn("SETTINGS_FAILED", logs)
            self.assertNotIn("ReferenceError:", logs)
            self.assertNotIn("TypeError:", logs)
