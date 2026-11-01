"""Status click semantics and advanced destinations, without device mutations."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'src/quickshell'

@unittest.skipUnless(os.environ.get('WAYLAND_DISPLAY'),'Status controls need Wayland')
class StatusNavigationTests(unittest.TestCase):
    def test_primary_sidebar_secondary_quick_controls_and_advanced_links(self):
        with tempfile.TemporaryDirectory(prefix='ai-status-navigation-') as temporary:
            base=Path(temporary)
            for name in ('modules','assets','scripts','defaults','translations','GlobalStates.qml'):(base/name).symlink_to(SOURCE/name)
            (base/'services').mkdir()
            for entry in (SOURCE/'services').iterdir():
                if entry.name=='SettingsNavigation.qml':
                    (base/'services'/entry.name).write_text('pragma Singleton\nimport Quickshell\nSingleton { property var calls:[];function open(section,detail){calls=[...calls,{section:section,detail:detail||""}];}}')
                else:(base/'services'/entry.name).symlink_to(entry)
            (base/'shell.qml').write_text('''//@ pragma UseQApplication
import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Wayland
import qs
import qs.services
import qs.modules.shared
import qs.modules.desktop.quickPanels
import qs.modules.desktop.sidebarRight
import qs.modules.desktop.sidebarRight.quickToggles
ShellRoot {
 id:root
 property bool complete:false
 property int editStep:0
 property var expectedToggles:[]
 property var originalToggles:[]
 function expect(condition,message){if(!condition)throw new Error(message);}
 function findToggle(item,type){if(item.buttonData?.type===type&&typeof item.editToggle==="function")return item;for(const child of item.children||[]){const found=findToggle(child,type);if(found)return found;}return null;}
 function verifyToggles(){
  const actual=Config.options.sidebar.quickToggles.android.toggles;
  expect(JSON.stringify(Array.from(actual,t=>({type:t.type,size:t.size})))===JSON.stringify(expectedToggles),"configuration differs at step "+editStep+": "+JSON.stringify(actual)+" expected "+JSON.stringify(expectedToggles));
  for(const toggle of expectedToggles){const button=findToggle(editor,toggle.type);expect(button&&button.cellSize===toggle.size,"wrong rendered toggle: "+toggle.type);}
 }
 function find(item,name){if(item.objectName===name)return item;for(const child of item.children||[]){const found=find(child,name);if(found)return found;}return null;}
 PanelWindow {
  implicitWidth:450;implicitHeight:180;exclusiveZone:0
  WlrLayershell.namespace:"quickshell:status-navigation-test";WlrLayershell.keyboardFocus:WlrKeyboardFocus.None
  mask:Region{}
  ColumnLayout {
   anchors.fill:parent
   RowLayout {
    id:buttons;spacing:Appearance.sizes.statusIconSpacing
    StatusPanelButton{id:sound;section:"audio";materialIcon:"volume_up"}
    StatusPanelButton{id:network;section:"network";materialIcon:"lan"}
    StatusPanelButton{id:bluetooth;section:"bluetooth";materialIcon:"bluetooth"}
   }
   SidebarRightContent{id:sidebar;visible:false;implicitHeight:800;Layout.preferredWidth:420;Layout.preferredHeight:800}
   AndroidQuickPanel{id:editor;visible:false;editMode:true;Layout.preferredWidth:400}
  }
 }
 Timer {
  interval:250;running:true
  onTriggered:{try{
   for(const button of [sound,network,bluetooth]){
    root.expect(button.width===Appearance.sizes.statusIconWidth&&button.height===Appearance.sizes.statusIconHeight,"unequal icon cells");
    GlobalStates.sidebarRightOpen=false;
    button.click();
    root.expect(GlobalStates.sidebarRightOpen&&!QuickPanelState.section,"left click did not open sidebar");
    button.altAction();
    root.expect(!GlobalStates.sidebarRightOpen&&QuickPanelState.section===button.section&&button.controller.opened,"right click did not open correct quick menu");
    button.click();
    root.expect(GlobalStates.sidebarRightOpen&&!QuickPanelState.section&&!button.controller.opened,"left click did not replace quick menu with sidebar");
    button.click();
    root.expect(!GlobalStates.sidebarRightOpen,"left click did not close sidebar");
   }
   root.expect(Math.abs((network.x-sound.x)-(bluetooth.x-network.x))<.1,"unequal icon spacing");
   for(const section of ["audio","network","bluetooth"]){
    GlobalStates.sidebarRightOpen=true;
    const toggle=root.findToggle(sidebar,section);
    root.expect(toggle!==null,"missing customizable toggle "+section);
    toggle.openMenu();
    root.expect(!GlobalStates.sidebarRightOpen,"advanced link did not dismiss sidebar");
    root.expect(SettingsNavigation.calls[SettingsNavigation.calls.length-1].section===section,"wrong advanced settings destination");
   }
   root.originalToggles=Array.from(Config.options.sidebar.quickToggles.android.toggles,t=>({type:t.type,size:t.size}));
   root.expectedToggles=[{type:"network",size:2},{type:"audio",size:2},{type:"bluetooth",size:1},{type:"mic",size:1}];
   Config.options.sidebar.quickToggles.android.toggles=root.expectedToggles;
   editing.start();
  }catch(error){console.error("STATUS_NAVIGATION_FAILED",error);Qt.quit();}}
 }
 Timer {
  id:editing;interval:120;repeat:true
  onTriggered:{try{
   root.verifyToggles();
   const sequence=[
    ["network","enabled"], ["bluetooth","enabled"], ["network","enabled"],
    ["bluetooth","enabled"], ["audio","move",1], ["network","size"],
    ["mic","enabled"], ["mic","enabled"], ["audio","move",-1]
   ];
   if(root.editStep>=sequence.length){
    stop();Config.options.sidebar.quickToggles.android.toggles=root.originalToggles;root.complete=true;return;
   }
   const [type,action,offset]=sequence[root.editStep++];
   const button=root.findToggle(editor,type);
   root.expect(button!==null,"missing editable button "+type);
   const expected=root.expectedToggles.map(t=>({type:t.type,size:t.size}));
   const index=expected.findIndex(t=>t.type===type);
   if(action==="enabled"){if(index<0)expected.push({type:type,size:1});else expected.splice(index,1);}
   else if(action==="size")expected[index].size=expected[index].size===1?2:1;
   else {const target=index+offset;if(target>=0&&target<expected.length)[expected[index],expected[target]]=[expected[target],expected[index]];}
   root.expectedToggles=expected;
   button.editToggle(type,action,offset||0);
  }catch(error){console.error("STATUS_NAVIGATION_FAILED",error);Qt.quit();}}
 }
 Timer {
  interval:100;running:root.complete;repeat:true
  onTriggered:if(!AudioControl.busy&&!AudioControl.refreshPending&&!NetworkControl.busy){console.log("STATUS_NAVIGATION_OK");Qt.quit();}
 }
 Timer{interval:8000;running:true;onTriggered:{console.error("STATUS_NAVIGATION_FAILED timeout");Qt.quit();}}
}''')
            env=dict(os.environ,DOTS_SHELL_SOURCE=str(base),XDG_CONFIG_HOME=str(base/'config'),XDG_STATE_HOME=str(base/'state'),XDG_CACHE_HOME=str(base/'cache'))
            launcher=env.get('DOTS_TEST_LAUNCHER')
            result=subprocess.run([launcher] if launcher else [shutil.which('quickshell'),'-p',str(base)],env=env,capture_output=True,text=True,timeout=12)
            logs=result.stdout+result.stderr
            self.assertEqual(result.returncode,0,logs);self.assertIn('STATUS_NAVIGATION_OK',logs)
            for error in ('TypeError:','ReferenceError:','Cannot assign','Binding loop','Unable to assign','STATUS_NAVIGATION_FAILED'):self.assertNotIn(error,logs)
