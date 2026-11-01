"""Xray preference, user interaction and compositor synchronization with a fake IPC."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/quickshell'


@unittest.skipUnless(os.environ.get('WAYLAND_DISPLAY'), 'Quickshell needs Wayland')
class XrayTests(unittest.TestCase):
    def test_toggle_and_compositor_sync(self):
        with tempfile.TemporaryDirectory(prefix='ai-xray-') as temporary:
            base = Path(temporary)
            for name in ('modules', 'assets', 'scripts', 'defaults', 'translations', 'GlobalStates.qml'):
                (base / name).symlink_to(SOURCE / name)
            log = base / 'commands.jsonl'
            fake = base / 'hyprctl'
            fake.write_text('#!/usr/bin/env python3\nimport json,sys\nfrom pathlib import Path\n'
                            + 'with Path(' + repr(str(log)) + ').open("a") as output: output.write(json.dumps(sys.argv[1:])+"\\n")\nprint("ok")\n')
            fake.chmod(0o755)
            (base / 'services').mkdir()
            for entry in (SOURCE / 'services').iterdir():
                if entry.name == 'LayerEffects.qml':
                    (base / 'services' / entry.name).write_text(entry.read_text().replace('["hyprctl",', '[' + json.dumps(str(fake)) + ','))
                else:
                    (base / 'services' / entry.name).symlink_to(entry)
            (base / 'shell.qml').write_text('''//@ pragma UseQApplication
import QtQuick
import Quickshell
import qs.services
import qs.modules.shared
import qs.modules.settings
ShellRoot {
    id:root
    property int phase:0
    property var page:null
    property var control:null
    property Component themePage: ThemeConfig { width:800 }
    function expect(condition,message){if(!condition)throw new Error(message);}
    function find(item,name){if(item.objectName===name)return item;for(const child of item.children||[]){const found=find(child,name);if(found)return found;}return null;}
    Timer {
        interval:200;running:true;repeat:true
        onTriggered:{try{
            if(!Config.ready)return;
            if(root.phase===0){
                root.expect(Config.options.appearance.transparency.xray,"existing appearance changed by default");
                root.page=root.themePage.createObject(root);
                root.control=root.find(root.page,"transparency-xray-control");
                root.expect(root.control&&root.control.checked,"missing Xray control");
                root.expect(Config.options.appearance.transparency.xray,"initialization modified preference");
                LayerEffects.load();
            }else if(root.phase===1){
                root.control.click();
                root.expect(!Config.options.appearance.transparency.xray,"click did not disable Xray");
            }else if(root.phase===2){
                root.expect(!LayerEffects.xray&&!root.control.checked,"disabled preference did not propagate");
                root.control.click();
                root.expect(Config.options.appearance.transparency.xray,"click did not re-enable Xray");
            }else if(root.phase===3){
                root.expect(LayerEffects.xray,"enabled preference did not propagate");
                LayerEffects.schedule(); // Same resynchronization path used after config reload.
            }else{
                console.log("XRAY_OK");Qt.quit();return;
            }
            root.phase++;
        }catch(error){console.error("XRAY_FAILED",error);Qt.quit();}}
    }
    Timer{interval:8000;running:true;onTriggered:{console.error("XRAY_FAILED timeout");Qt.quit();}}
}''')
            env = dict(os.environ, DOTS_SHELL_SOURCE=str(base), XDG_CONFIG_HOME=str(base / 'config'),
                       XDG_STATE_HOME=str(base / 'state'), XDG_CACHE_HOME=str(base / 'cache'))
            launcher = env.get('DOTS_TEST_LAUNCHER')
            result = subprocess.run([launcher] if launcher else [shutil.which('quickshell'), '-p', str(base)],
                                    env=env, capture_output=True, text=True, timeout=12)
            logs = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, logs)
            self.assertIn('XRAY_OK', logs)
            for error in ('XRAY_FAILED', 'TypeError:', 'ReferenceError:', 'Cannot assign', 'Binding loop', 'Unable to assign'):
                self.assertNotIn(error, logs)
            commands = [json.loads(line) for line in log.read_text().splitlines()]
            self.assertGreaterEqual(len(commands), 3)
            self.assertTrue(any('xray=false});' in command[-1] for command in commands))
            self.assertTrue(any('xray=true});' in command[-1] for command in commands))
            for command in commands:
                self.assertEqual(command[:2], ['-r', 'eval'])
                self.assertIn('name="artificial-impulse-xray"', command[-1])
                self.assertIn('namespace="^quickshell:.*$"', command[-1])
                self.assertIn('namespace="^quickshell:popup$"},xray=false', command[-1])
                self.assertIn('name="artificial-impulse-bar-animation",match={namespace="^quickshell:bar$"},no_anim=true', command[-1])
                self.assertNotIn('hl.config', command[-1])
