"""Exercise the real QML service with an isolated, deterministic IPC backend."""
import collections
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "src/quickshell/services/HyprlandData.qml"

FAKE_HYPRCTL = '''#!/usr/bin/env python3
import json, os, sys, time
from pathlib import Path
name = sys.argv[1]
log = Path(os.environ['FAKE_HYPRCTL_LOG'])
previous = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
number = 1 + sum(row['name'] == name and row['phase'] == 'start' for row in previous)
with log.open('a') as output:
    output.write(json.dumps(dict(name=name, phase='start', time=time.monotonic(), number=number)) + '\\n')
if name == 'clients': time.sleep(float(os.environ.get('FAKE_CLIENT_DELAY', '0')))
data = {
    'clients': [dict(address='0x1', title='run-' + str(number), workspace=dict(id=1), size=[100, 100])],
    'workspaces': [dict(id=1), dict(id=5000)],
    'activeworkspace': dict(id=1, monitor='TEST'),
    'monitors': [dict(id=0, name='TEST')],
    'layers': dict(TEST={})
}[name]
print(json.dumps(data))
with log.open('a') as output:
    output.write(json.dumps(dict(name=name, phase='end', time=time.monotonic(), number=number)) + '\\n')
'''


@unittest.skipUnless(os.environ.get("WAYLAND_DISPLAY"), "A Wayland connection is needed to load Quickshell")
class HyprlandRefreshTests(unittest.TestCase):
    def test_full_shell_type_graph_loads(self):
        with tempfile.TemporaryDirectory(prefix="dots-shell-types-") as temporary:
            base = Path(temporary)
            source = ROOT / "src/quickshell"
            for name in ("modules", "services", "shellVariants", "assets", "scripts", "defaults", "translations", "GlobalStates.qml"):
                (base / name).symlink_to(source / name, target_is_directory=(source / name).is_dir())
            (base / "shell.qml").write_text('''//@ pragma UseQApplication
import QtQuick
import Quickshell
import "shellVariants"
ShellRoot {
    property Component primaryPanels: Component { DesktopShell {} }
    property Component alternatePanels: Component { WindowsStyleShell {} }
    Timer { interval: 300; running: true; onTriggered: { console.log("SHELL_TYPES_OK"); Qt.quit(); } }
}
''')
            env = dict(os.environ, DOTS_SHELL_SOURCE=str(base), HYPRLAND_INSTANCE_SIGNATURE="isolated-refresh-test",
                       XDG_CONFIG_HOME=str(base / "config"), XDG_STATE_HOME=str(base / "state"),
                       XDG_CACHE_HOME=str(base / "cache"))
            launcher = env.get("DOTS_TEST_LAUNCHER")
            command = [launcher] if launcher else [shutil.which("quickshell"), "-p", str(base)]
            result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=10)
            logs = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, logs)
            self.assertIn("SHELL_TYPES_OK", logs)

    def run_service(self, timers, final_assertions, duration=1100, delay="0"):
        with tempfile.TemporaryDirectory(prefix="dots-refresh-") as temporary:
            base = Path(temporary)
            (base / "services").mkdir()
            shutil.copy2(SERVICE, base / "services/HyprlandData.qml")
            shutil.copytree(SERVICE.parent / "hyprland", base / "services/hyprland")
            (base / "bin").mkdir()
            backend = base / "bin/hyprctl"
            backend.write_text(FAKE_HYPRCTL)
            backend.chmod(0o755)
            (base / "shell.qml").write_text('''//@ pragma UseQApplication
import QtQuick
import Quickshell
import "services"
ShellRoot {
    property var service: HyprlandData
    property int changes: 0
    property int baselineChanges: 0
    Connections {
        target: HyprlandData
        function onWindowListChanged() { changes++; }
    }
''' + timers + f'''
    Timer {{
        interval: {duration}; running: true
        onTriggered: {{
            {final_assertions}
            console.log("REFRESH_TEST_OK");
            Qt.quit();
        }}
    }}
    Timer {{ interval: 4000; running: true; onTriggered: Qt.quit(); }}
}}
''')
            env = dict(os.environ, DOTS_SHELL_SOURCE=str(base), HYPRLAND_INSTANCE_SIGNATURE="isolated-refresh-test",
                       XDG_CONFIG_HOME=str(base / "config"), XDG_STATE_HOME=str(base / "state"),
                       XDG_CACHE_HOME=str(base / "cache"), FAKE_HYPRCTL_LOG=str(base / "calls.jsonl"),
                       FAKE_CLIENT_DELAY=delay, PATH=str(base / "bin") + ":" + os.environ["PATH"])
            launcher = env.get("DOTS_TEST_LAUNCHER")
            command = [launcher] if launcher else [shutil.which("quickshell"), "-p", str(base)]
            result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=10)
            logs = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, logs)
            self.assertIn("REFRESH_TEST_OK", logs, logs)
            self.assertNotIn("Failed to load configuration", logs)
            return [json.loads(line) for line in (base / "calls.jsonl").read_text().splitlines()]

    def test_window_burst_queries_only_affected_data(self):
        calls = self.run_service('''
    Timer { interval: 350; running: true; onTriggered: {
        for (let i = 0; i < 40; i++) service.handleEvent("openwindow");
    }}
''', '''
            if (service.windowList.length !== 1 || service.workspaceIds.length !== 1)
                throw new Error("Desktop state did not load");
''')
        count = collections.Counter(row["name"] for row in calls if row["phase"] == "start")
        self.assertEqual(count, {"clients": 2, "workspaces": 2, "activeworkspace": 2, "monitors": 1, "layers": 1})

    def test_updates_arriving_during_slow_query_are_not_lost_or_cancelled(self):
        calls = self.run_service('''
    Timer { interval: 100; running: true; onTriggered: service.handleEvent("windowtitle") }
    Timer { interval: 150; running: true; onTriggered: service.handleEvent("windowtitlev2") }
''', '''
            if (service.windowList[0]?.title !== "run-2") throw new Error("Latest update was lost");
''', duration=1300, delay="0.25")
        clients = [row for row in calls if row["name"] == "clients"]
        self.assertEqual([row["phase"] for row in clients], ["start", "end", "start", "end"])

    def test_duplicate_or_invalid_payloads_keep_existing_state(self):
        self.run_service('''
    Timer { interval: 350; running: true; onTriggered: {
        baselineChanges = changes;
        service.applyResult("clients", service.lastPayloads.clients);
        service.applyResult("clients", "{broken");
        service.applyResult("clients", "null");
        service.applyResult("clients", "{}");
    }}
''', '''
            if (changes !== baselineChanges || service.windowList[0]?.address !== "0x1")
                throw new Error("A duplicate or invalid response changed valid state");
''')

    def test_continuous_events_do_not_starve_refresh(self):
        calls = self.run_service('''
    Timer { interval: 300; running: true; onTriggered: events.start() }
    Timer { id: events; interval: 15; repeat: true; onTriggered: service.handleEvent("windowtitle") }
''', '''events.stop();''', duration=1000)
        updates = [row for row in calls if row["name"] == "clients" and row["phase"] == "start" and row["number"] > 1]
        self.assertGreaterEqual(len(updates), 3)
        self.assertLess(len(updates), 20)
