"""Exercise QML -> helper stdin -> preview/keep/revert with simulated IPC."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/quickshell"


@unittest.skipUnless(os.environ.get("WAYLAND_DISPLAY"), "Quickshell needs a Wayland connection")
class DesktopWorkflowTests(unittest.TestCase):
    def test_draft_preview_keep_and_revert_round_trip(self):
        spec = importlib.util.spec_from_file_location("workflow_schema", SOURCE / "scripts/hyprland/desktop.py")
        schema = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(schema)
        with tempfile.TemporaryDirectory(prefix="desktop-workflow-") as directory:
            base = Path(directory)
            for name in ("modules", "services", "assets", "scripts", "defaults", "translations", "GlobalStates.qml"):
                (base / name).symlink_to(SOURCE / name, target_is_directory=(SOURCE / name).is_dir())
            hypr = base / "config/hypr"
            (hypr / "hyprland/services").mkdir(parents=True)
            (hypr / "hyprland.lua").write_text(schema.HOOK + "\n")
            (hypr / "hyprland/services/desktop.lua").write_text("-- fixture only\n")
            tools = base / "bin"
            tools.mkdir()
            fake = tools / "hyprctl"
            fake.write_text("#!" + sys.executable + "\n" + '''
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
base = Path(os.environ['DESKTOP_WORKFLOW_FIXTURE'])
fields = json.loads((base / 'fields.json').read_text())
with (base / 'calls.jsonl').open('a') as log: log.write(json.dumps(args) + '\\n')
if args[0] == 'monitors': print('[]')
elif args[0] == 'devices': print('{"mice": [], "keyboards": []}')
elif args[0] == 'getoption':
    field = fields[args[1]]
    kind = {'bool':'bool','int':'int','float':'float','gap':'css'}.get(field['type'], 'str')
    print(json.dumps({kind: field['default']}))
elif args[0] == 'configerrors': print('')
elif args[0] == 'eval' and args[1].startswith('-'):
    print('usage: hyprctl [flags] <command>', file=sys.stderr); sys.exit(1)
else: print('ok')
''')
            fake.chmod(0o755)
            (base / "fields.json").write_text(json.dumps(schema.BY_KEY))
            (base / "shell.qml").write_text('''//@ pragma UseQApplication
import QtQuick
import Quickshell
import Quickshell.Io
import qs.services
import qs.modules.settings
import Quickshell.Wayland
ShellRoot {
    Process {
        id: externalRevert
        stdout: StdioCollector {}
    }
    DesktopPreviewPrompt { id: confirmation; screen: Quickshell.screens[0]; WlrLayershell.keyboardFocus: WlrKeyboardFocus.None }
    Component.onCompleted: DesktopSettings.refresh()
    Timer {
        interval: 100; running: true; repeat: true
        property int phase: 0
        onTriggered: {
            if (DesktopSettings.busy) return;
            if (DesktopSettings.failed) {
                console.error("DESKTOP_WORKFLOW_FAILED", DesktopSettings.message); Qt.quit(); return;
            }
            if (phase === 0 && DesktopSettings.loaded) {
                if (DesktopSettings.changes !== 0) { console.error("DIRTY_ON_OPEN"); Qt.quit(); return; }
                DesktopSettings.put("options", "decoration:rounding", 22);
                DesktopSettings.preview(); phase++;
            } else if (phase === 1 && DesktopSettings.transaction) {
                if (DesktopSettings.saved.options["decoration:rounding"] !== undefined) { console.error("SAVED_BEFORE_CONFIRM"); Qt.quit(); return; }
                DesktopSettings.keep(); phase++;
            } else if (phase === 2 && !DesktopSettings.transaction && DesktopSettings.saved.options["decoration:rounding"] === 22) {
                DesktopSettings.put("options", "decoration:rounding", 25);
                DesktopSettings.preview(); phase++;
            } else if (phase === 3 && DesktopSettings.transaction) {
                DesktopSettings.revert();
                if (confirmation.visible) { console.error("REVERT_PROMPT_STILL_VISIBLE"); Qt.quit(); return; }
                phase++;
            } else if (phase === 4 && !DesktopSettings.transaction && DesktopSettings.changes === 0) {
                if (confirmation.visible) { console.error("REVERT_PROMPT_REOPENED"); Qt.quit(); return; }
                DesktopSettings.put("options", "decoration:rounding", 26);
                DesktopSettings.preview(); phase++;
            } else if (phase === 5 && DesktopSettings.transaction) {
                externalRevert.command = ["python3", Quickshell.shellPath("scripts/hyprland/desktop.py"), "revert", DesktopSettings.transaction.token];
                externalRevert.running = true; phase++;
            } else if (phase === 6 && !DesktopSettings.transaction && DesktopSettings.changes === 0) {
                if (confirmation.visible) { console.error("EXTERNAL_REVERT_PROMPT_REMAINED"); Qt.quit(); return; }
                console.log("DESKTOP_WORKFLOW_OK"); Qt.quit();
            }
        }
    }
    Timer { interval: 12000; running: true; onTriggered: { console.error("DESKTOP_WORKFLOW_TIMEOUT"); Qt.quit(); } }
}
''')
            environment = dict(os.environ, DOTS_SHELL_SOURCE=str(base), HYPRLAND_INSTANCE_SIGNATURE="isolated-desktop-workflow",
                               XDG_CONFIG_HOME=str(base / "config"), XDG_STATE_HOME=str(base / "state"),
                               XDG_CACHE_HOME=str(base / "cache"), DESKTOP_WORKFLOW_FIXTURE=str(base),
                               PATH=str(tools) + os.pathsep + os.environ["PATH"])
            launcher = environment.get("DOTS_TEST_LAUNCHER")
            command = [launcher] if launcher else [shutil.which("quickshell"), "-p", str(base)]
            try:
                result = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=18)
                logs = result.stdout + result.stderr
                self.assertEqual(result.returncode, 0, logs)
                self.assertIn("DESKTOP_WORKFLOW_OK", logs)
                self.assertNotIn("ReferenceError:", logs)
                self.assertNotIn("TypeError:", logs)
                saved = json.loads((base / "config/artificial-impulse/hyprland.json").read_text())
                self.assertEqual(saved["options"], {"decoration:rounding": 22})
                self.assertIn('["rounding"]=22', (base / "config/artificial-impulse/hyprland.lua").read_text())
            finally:
                (base / "state/artificial-impulse/desktop/pending.json").unlink(missing_ok=True)
                time.sleep(1.1)  # Let detached fixture guards observe cancellation before cleanup.

    def test_failed_restore_pauses_polling_and_queued_retry_closes_prompt(self):
        with tempfile.TemporaryDirectory(prefix="desktop-restore-error-") as directory:
            base = Path(directory)
            for name in ("modules", "services", "assets", "defaults", "translations", "GlobalStates.qml"):
                (base / name).symlink_to(SOURCE / name)
            scripts = base / "scripts/hyprland"
            scripts.mkdir(parents=True)
            (scripts / "desktop.py").write_text('''
import json, pathlib, sys, time
base = pathlib.Path(__file__).resolve().parents[2]
state = base / 'state.json'
data = json.loads(state.read_text()) if state.exists() else {'reverts': 0}
action = sys.argv[1]
with (base / 'calls.jsonl').open('a') as output: output.write(json.dumps(action) + '\\n')
transaction = None if data['reverts'] >= 2 else dict(token='test-token', deadline=time.time()-1,
    phase='restore_failed' if data['reverts'] else 'active', error='fixture restore failure')
if action == 'transaction': time.sleep(.3)
if action == 'revert':
    data['reverts'] += 1
    state.write_text(json.dumps(data))
    transaction = None if data['reverts'] >= 2 else dict(transaction, phase='restore_failed')
    if transaction:
        print(json.dumps(dict(ok=False, error='fixture restore failure', transaction=transaction)))
        sys.exit(1)
result = dict(ok=True, transaction=transaction)
if action == 'snapshot': result.update(monitors=[],devices=[],fields=[],values={},supported={},
    saved=dict(options={},monitors={},devices={}),integrated=True)
print(json.dumps(result))
''')
            (base / "shell.qml").write_text('''//@ pragma UseQApplication
import QtQuick
import Quickshell
import Quickshell.Wayland
import qs.services
import qs.modules.settings
ShellRoot {
    property int phase: 0
    property int pausedTicks: 0
    DesktopPreviewPrompt { id: prompt; screen: Quickshell.screens[0]; WlrLayershell.keyboardFocus: WlrKeyboardFocus.None }
    Timer {
        interval: 100; repeat: true; running: true
        onTriggered: {
            if (DesktopSettings.busy) return;
            if (phase === 0 && DesktopSettings.transaction) {
                DesktopSettings.request("transaction");
                DesktopSettings.revert();
                if (!DesktopSettings.pendingResolution || prompt.visible) {
                    console.error("RESTORE_ERROR_FAILED resolution lost during background query"); Qt.quit(); return;
                }
                phase++; return;
            }
            if (phase === 1) {
                if (!DesktopSettings.restorationFailed || !DesktopSettings.transactionPollingPaused || !prompt.visible) {
                    console.error("RESTORE_ERROR_FAILED no explicit failed state"); Qt.quit(); return;
                }
                // Let more than two poll intervals pass without automatic retries.
                if (++pausedTicks < 25) return;
                DesktopSettings.revert(); phase++; return;
            }
            if (phase === 2 && !DesktopSettings.transaction) {
                if (prompt.visible) { console.error("RESTORE_ERROR_FAILED prompt reopened"); Qt.quit(); return; }
                console.log("RESTORE_ERROR_OK"); Qt.quit();
            }
        }
    }
    Timer { interval: 10000; running: true; onTriggered: { console.error("RESTORE_ERROR_FAILED timeout"); Qt.quit(); } }
}
''')
            env = dict(os.environ, DOTS_SHELL_SOURCE=str(base), XDG_CONFIG_HOME=str(base / "config"),
                       XDG_STATE_HOME=str(base / "state"), XDG_CACHE_HOME=str(base / "cache"))
            launcher = env.get("DOTS_TEST_LAUNCHER")
            command = [launcher] if launcher else [shutil.which("quickshell"), "-p", str(base)]
            result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=15)
            logs = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, logs)
            self.assertIn("RESTORE_ERROR_OK", logs)
            self.assertNotIn("RESTORE_ERROR_FAILED", logs)
            self.assertNotIn("TypeError:", logs)
            calls = [json.loads(line) for line in (base / "calls.jsonl").read_text().splitlines()]
            self.assertEqual(calls.count("transaction"), 2, calls)
            self.assertEqual(calls.count("revert"), 2, calls)
