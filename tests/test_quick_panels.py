"""Read-only quick panel lifecycle, mutual exclusion and constrained geometry."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'src/quickshell'

@unittest.skipUnless(os.environ.get('WAYLAND_DISPLAY'),'Quick panels need Wayland')
class QuickPanelTests(unittest.TestCase):
    def test_three_panels_open_exclusively_and_fit_screen(self):
        with tempfile.TemporaryDirectory(prefix='ai-quick-panels-') as temporary:
            base=Path(temporary)
            for name in ('modules','assets','scripts','defaults','translations','GlobalStates.qml'):(base/name).symlink_to(SOURCE/name)
            (base/'services').mkdir()
            for entry in (SOURCE/'services').iterdir():
                if entry.name=='GlobalFocusGrab.qml':
                    # Keep real registration/lifecycle, without stealing the user's focus.
                    (base/'services'/entry.name).write_text(entry.read_text().replace('active: root.dismissable.length > 0','active: false'))
                else:(base/'services'/entry.name).symlink_to(entry)
            (base/'shell.qml').write_text('''//@ pragma UseQApplication
import QtQuick
import Quickshell
import Quickshell.Wayland
import qs.services
import qs.modules.shared
import qs.modules.desktop.quickPanels
ShellRoot {
 id:root
 property int phase:0
 property var frame:null
 property var firstFrame:null
 function find(item,name){if(item.objectName===name)return item;for(const child of item.children||[]){const found=find(child,name);if(found)return found;}return null;}
 function fail(message){console.error("QUICK_FAILED",message);Qt.quit();}
 QuickPanel{}
 Timer {
  interval:60;running:true;repeat:true
  onTriggered:{
   const windows=GlobalFocusGrab.dismissable.filter(w=>w.visible);
   if(root.phase===0){AudioControl.open();root.phase=1;return;}
   if(root.phase===9){
    if(windows.length||QuickPanelState.section){root.fail("close left a visible window");return;}
    root.frame=null;AudioControl.open();root.phase=10;return;
   }
   if(windows.length!==1){root.fail("window count during transition: "+windows.length);return;}
   const window=windows[0];
   if(window.exclusionMode!==ExclusionMode.Normal||Math.abs(window.margins.top+Appearance.sizes.elevationMargin-Appearance.sizes.hyprlandGapsOut)>0.1){root.fail("popup gap does not match sidebar");return;}
   if(root.frame&&root.frame!==window){root.fail("window recreated when switching");return;}
   if(!root.frame){root.frame=window;if(root.phase===1)root.firstFrame=window;}
   const body=root.find(window.contentItem,"quick-panel-body");
   const content=root.find(window.contentItem,"quick-panel-content");
   if(window.transitioning&&body.enabled){root.fail("interactive transition");return;}
   if(window.phase==="resize"&&body.opacity>0){root.fail("content visible while switching height");return;}
   if(content.item&&content.item.objectName!=="quick-content-"+window.displayedSection){root.fail("overlapping/stale content");return;}
   if(root.phase===5&&(window.phase==="resize"||window.phase==="in"||window.phase==="idle")){
    BluetoothManager.open(window.screen.name);root.phase=6;return;
   }
   if(window.phase!=="idle")return;
   if(Math.abs(window.width-window.implicitWidth)>1||Math.abs(window.height-window.implicitHeight)>1)return;
   if(window.width>420||window.height>window.screen.height*.8||window.height<150){root.fail("geometry");return;}
   if(root.phase===1){
    if(window.displayedSection!=="audio"){root.fail("audio not displayed");return;}
    console.log("QUICK_PANEL_OK audio");NetworkControl.open(window.screen.name);root.phase=2;
   }else if(root.phase===2){
    if(window.displayedSection!=="network"){root.fail("network not displayed");return;}
    console.log("QUICK_PANEL_OK network");BluetoothManager.open(window.screen.name);root.phase=3;
   }else if(root.phase===3){
    if(window.displayedSection!=="bluetooth"){root.fail("Bluetooth not displayed");return;}
    console.log("QUICK_PANEL_OK bluetooth");
    AudioControl.open(window.screen.name);NetworkControl.open(window.screen.name);BluetoothManager.open(window.screen.name);NetworkControl.open(window.screen.name);root.phase=4;
   }else if(root.phase===4){
    if(window.displayedSection!=="network"){root.fail("rapid switching did not settle on latest request");return;}
    console.log("QUICK_SWITCH_IDENTITY_OK");
    AudioControl.open(window.screen.name);root.phase=5;
   }else if(root.phase===6){
    if(window.displayedSection!=="bluetooth"){root.fail("resize interruption did not use latest selection");return;}
    NetworkControl.open(window.screen.name);GlobalFocusGrab.dismiss();root.phase=9;
   }else if(root.phase===10){
    if(window===root.firstFrame){root.fail("closed window was not released");return;}
    AudioControl.close();console.log("QUICK_PANELS_OK");Qt.quit();
   }
  }
 }
 Timer{interval:15000;running:true;onTriggered:{console.error("QUICK_TIMEOUT");Qt.quit();}}
}''')
            env=dict(os.environ,DOTS_SHELL_SOURCE=str(base),XDG_CONFIG_HOME=str(base/'config'),XDG_STATE_HOME=str(base/'state'),XDG_CACHE_HOME=str(base/'cache'))
            launcher=env.get('DOTS_TEST_LAUNCHER')
            result=subprocess.run([launcher] if launcher else [shutil.which('quickshell'),'-p',str(base)],env=env,capture_output=True,text=True,timeout=20)
            logs=result.stdout+result.stderr
            self.assertEqual(result.returncode,0,logs)
            self.assertIn('QUICK_PANELS_OK',logs)
            self.assertIn('QUICK_SWITCH_IDENTITY_OK',logs)
            for section in ('audio','network','bluetooth'):self.assertIn('QUICK_PANEL_OK '+section,logs)
            for error in ('ReferenceError:','TypeError:','Cannot assign','Binding loop','Unable to assign','QUICK_GEOMETRY','QUICK_WINDOW_COUNT','QUICK_FAILED'):self.assertNotIn(error,logs)
