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

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "dots/.config/quickshell/ii"


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
else: print('ok')
''')
            fake.chmod(0o755)
            (base / "fields.json").write_text(json.dumps(schema.BY_KEY))
            (base / "shell.qml").write_text('''//@ pragma UseQApplication
import QtQuick
import Quickshell
import qs.services
ShellRoot {
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
                DesktopSettings.revert(); phase++;
            } else if (phase === 4 && !DesktopSettings.transaction && DesktopSettings.changes === 0) {
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
