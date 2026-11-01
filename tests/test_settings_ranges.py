"""Verify draft-only range edits, decimal input and external reset bindings."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'src/quickshell'


@unittest.skipUnless(os.environ.get('WAYLAND_DISPLAY'),'QML controls need Wayland')
class SettingsRangeTests(unittest.TestCase):
    def test_slider_numeric_edit_validation_and_external_reset(self):
        with tempfile.TemporaryDirectory(prefix='ai-settings-range-') as temporary:
            base=Path(temporary)
            for name in ('modules','services','assets','scripts','defaults','translations','GlobalStates.qml'):
                (base/name).symlink_to(SOURCE/name,target_is_directory=(SOURCE/name).is_dir())
            fixture='''//@ pragma UseQApplication
import QtQuick
import Quickshell
import qs.modules.settings
ShellRoot {
    id: root
    property real saved: 0.6
    property int edits: 0
    property int phase: 0
    PanelWindow {
        visible: false
        implicitWidth: 440; implicitHeight: 160
        SettingsRange {
            id: range; width: 400; from: -1; to: 1; value: root.saved
            onEdited: nextValue => { root.saved = nextValue; root.edits++; }
        }
    }
    Timer {
        interval: 250; running: true; repeat: true
        onTriggered: {
            function find(item,name) {
                if(item.objectName===name)return item;
                for(const child of item.children || []) { const found=find(child,name); if(found)return found; }
                return null;
            }
            const editor=find(range,"settings-range-value");
            const slider=find(range,"settings-range-slider");
            if (root.phase === 1) {
                slider.moved();
                if(root.saved!==-0.25 || range.invalid) { console.error("RANGE_SLIDER_FAILED", root.saved); Qt.quit(); return; }
                root.saved=0.4;
                if(editor.text!=="0.40") { console.error("RANGE_RESET_FAILED",editor.text); Qt.quit(); return; }
                console.log("SETTINGS_RANGE_OK"); Qt.quit(); return;
            }
            if(!editor || !slider || root.edits!==0) { console.error("RANGE_INIT_FAILED"); Qt.quit(); return; }
            editor.text="0.85"; editor.textEdited();
            if(root.saved!==0.85 || editor.text!=="0.85") { console.error("RANGE_LIVE_EDIT_FAILED"); Qt.quit(); return; }
            editor.text="0,75"; editor.textEdited();
            if(root.saved!==0.75) { console.error("RANGE_LOCALE_FAILED"); Qt.quit(); return; }
            editor.text="5"; editor.textEdited(); editor.editingFinished();
            if(root.saved!==0.75 || !range.invalid) { console.error("RANGE_VALIDATION_FAILED"); Qt.quit(); return; }
            slider.value=-0.25; root.phase=1;
        }
    }
}'''
            (base/'shell.qml').write_text(fixture)
            env=dict(os.environ,DOTS_SHELL_SOURCE=str(base),XDG_CONFIG_HOME=str(base/'config'),XDG_STATE_HOME=str(base/'state'),XDG_CACHE_HOME=str(base/'cache'))
            launcher=env.get('DOTS_TEST_LAUNCHER')
            command=[launcher] if launcher else [shutil.which('quickshell'),'-p',str(base)]
            result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=12)
            logs=result.stdout+result.stderr
            self.assertEqual(result.returncode,0,logs)
            self.assertIn('SETTINGS_RANGE_OK',logs)
            self.assertNotIn('TypeError:',logs)
            self.assertNotIn('ReferenceError:',logs)
