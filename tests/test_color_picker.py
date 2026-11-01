"""Color conversion, gradient stop preservation and the public Qt color dialog."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'src/quickshell'


class GradientParsingTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'),'Node is required for gradient parsing tests')
    def test_rgba_order_alpha_and_all_gradient_stops(self):
        script=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const context=vm.createContext({});
vm.runInContext(fs.readFileSync(process.argv[1],'utf8').replace(/^\.pragma library\s*/,''),context);
const parsed=context.parse('rgba(11223344) rgb(aabbcc) 125deg');
assert.equal(parsed.valid,true);
assert.equal(Array.from(parsed.colors).join(','),'11223344,aabbccff');
assert.equal(parsed.angle,125);
assert.equal(context.qtColor(parsed.colors[0]),'#44112233');
assert.equal(context.fromColor({r:0.2,g:0.4,b:0.6,a:0.5}),'33669980');
assert.equal(context.format(parsed.colors,125,true),'rgba(11223344) rgba(aabbccff) 125deg');
const many=Array(10).fill('rgba(abcdef80)').join(' ')+' 360deg';
assert.equal(context.parse(many).colors.length,10);
assert.equal(context.parse(many+' rgba(123456ff)').valid,false);
for(const value of ['', 'rgba(123)', 'rgba(11223344) 361deg', '#123456','rgb(abcdef);bad'])assert.equal(context.parse(value).valid,false);
'''
        result=subprocess.run([shutil.which('node'),'-e',script,str(SOURCE/'modules/shared/functions/GradientColors.js')],capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)


@unittest.skipUnless(os.environ.get('WAYLAND_DISPLAY'),'Qt color dialog needs Wayland')
class ColorPickerTests(unittest.TestCase):
    def test_color_dialog_cancel_accept_and_stop_editing(self):
        with tempfile.TemporaryDirectory(prefix='ai-color-picker-') as temporary:
            base=Path(temporary)
            for name in ('modules','services','assets','scripts','defaults','translations','GlobalStates.qml'):
                (base/name).symlink_to(SOURCE/name,target_is_directory=(SOURCE/name).is_dir())
            fixture='''//@ pragma UseQApplication
import QtQuick
import Quickshell
import Quickshell.Wayland
import qs.modules.settings
import qs.modules.shared
ShellRoot {
    id: root
    property string value: "rgba(11223344) rgba(aabbccff) 125deg"
    property int edits: 0
    property int phase: 0
    PanelWindow {
        visible:true; implicitWidth:700; implicitHeight:680; exclusiveZone:0
        color:Appearance.colors.colLayer0
        WlrLayershell.namespace:"quickshell:color-picker-test"
        WlrLayershell.layer:WlrLayer.Overlay
        WlrLayershell.keyboardFocus:WlrKeyboardFocus.None
        mask:Region {}
        GradientColorField {
            id: field
            x:20; y:20; width:660
            value:root.value
            onEdited: value => { root.value=value; root.edits++; }
        }
    }
    Timer {
        interval:200; running:true; repeat:true
        onTriggered:{
            if(root.phase===0){
                if(root.edits!==0 || !field.parsed.valid) { console.error("COLOR_INIT_FAILED"); Qt.quit(); return; }
                field.pick(0); root.phase++;
            }else if(root.phase===1){
                if(!field.picker.visible || Math.abs(field.picker.selectedColor.a-68/255)>0.005){ console.error("COLOR_ALPHA_FAILED",field.picker.selectedColor); Qt.quit(); return; }
                field.picker.selectedColor=Qt.rgba(1,0,0,1); field.picker.reject();
                if(root.edits!==0){ console.error("COLOR_CANCEL_CHANGED_DRAFT"); Qt.quit(); return; }
                field.pick(1); root.phase++;
            }else if(root.phase===2){
                field.picker.selectedColor=Qt.rgba(0.2,0.4,0.6,0.5); field.picker.accept(); root.phase++;
            }else{
                if(root.value!=="rgba(11223344) rgba(33669980) 125deg"){console.error("COLOR_ACCEPT_FAILED",root.value);Qt.quit();return;}
                field.addColor();
                if(field.parsed.colors.length!==3 || field.parsed.angle!==125){console.error("COLOR_ADD_FAILED");Qt.quit();return;}
                field.removeColor(2);
                if(field.parsed.colors.length!==2 || field.parsed.colors[1]!=="33669980"){console.error("COLOR_REMOVE_FAILED");Qt.quit();return;}
                console.log("COLOR_PICKER_OK");Qt.quit();
            }
        }
    }
    Timer{interval:8000;running:true;onTriggered:{console.error("COLOR_PICKER_TIMEOUT");Qt.quit();}}
}'''
            (base/'shell.qml').write_text(fixture)
            env=dict(os.environ,DOTS_SHELL_SOURCE=str(base),XDG_CONFIG_HOME=str(base/'config'),XDG_STATE_HOME=str(base/'state'),XDG_CACHE_HOME=str(base/'cache'))
            launcher=env.get('DOTS_TEST_LAUNCHER')
            command=[launcher] if launcher else [shutil.which('quickshell'),'-p',str(base)]
            result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=12)
            logs=result.stdout+result.stderr
            (ROOT/'work/color-picker-ui.log').write_text(logs)
            self.assertEqual(result.returncode,0,logs)
            self.assertIn('COLOR_PICKER_OK',logs)
            for failure in ('TypeError:','ReferenceError:','Cannot assign'):
                self.assertNotIn(failure,logs)
