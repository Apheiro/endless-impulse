"""Keep a real sidebar mapped, populated and unfocused until its live slide ends."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/quickshell'


@unittest.skipUnless(os.environ.get('WAYLAND_DISPLAY'), 'Quickshell needs Wayland')
class SidebarRevealTests(unittest.TestCase):
    def test_live_close_and_reopen(self):
        with tempfile.TemporaryDirectory(prefix='ai-sidebar-reveal-') as temporary:
            base = Path(temporary)
            for name in ('modules', 'assets', 'scripts', 'defaults', 'translations', 'GlobalStates.qml'):
                (base / name).symlink_to(SOURCE / name)
            (base / 'services').mkdir()
            for entry in (SOURCE / 'services').iterdir():
                if entry.name == 'GlobalFocusGrab.qml':
                    (base / 'services' / entry.name).write_text(entry.read_text().replace('active: root.dismissable.length > 0', 'active: false'))
                else:
                    (base / 'services' / entry.name).symlink_to(entry)
            (base / 'shell.qml').write_text('''//@ pragma UseQApplication
import QtQuick
import Quickshell
import qs
import qs.services
import qs.modules.shared
import qs.modules.desktop.sidebarRight
ShellRoot {
    id:root
    property int phase:0
    property var panel:null
    property real deadline:0
    property bool observedClose:false
    property bool observedOvershoot:false
    property bool observedLongOpening:false
    property double openingStarted:0
    function expect(condition,message){if(!condition)throw new Error(message);}
    function expectClickableContent() {
        const content=root.panel.contentItem.children.find(child=>child.sourceComponent!==undefined);
        root.expect(content&&content.item,"sidebar content was unloaded");
        const center=content.mapToItem(root.panel.contentItem,content.width/2,content.height/2);
        const input=root.panel.mask;
        root.expect(center.x>=input.x&&center.x<input.x+input.width&&center.y>=input.y&&center.y<input.y+input.height,
            "visible controls are outside the input region");
    }
    SidebarRight {}
    Timer {
        interval:25;running:true;repeat:true
        onTriggered:{try{
            if(!Config.ready)return;
            if(root.phase===0){
                root.expect(Config.options.appearance.animationDurations.sidebarOpen===600&&Config.options.appearance.animationDurations.sidebarClose===600,"sidebar defaults are not 600 ms");
                Config.options.appearance.animationDurations.sidebarOpen=600;
                Config.options.appearance.animationDurations.sidebarClose=200;
                Config.options.appearance.animationSpeed=1;
                Config.options.sidebar.keepRightSidebarLoaded=false;
                GlobalStates.sidebarRightOpen=true;
                root.openingStarted=Date.now();root.phase=1;root.deadline=Date.now()+800;return;
            }
            if(root.phase===1){
                const window=GlobalFocusGrab.dismissable[0];
                if(window){
                    const content=window.contentItem.children.find(child=>child.sourceComponent!==undefined);
                    const left=content.mapToItem(window.contentItem,0,0).x;
                    const elapsed=Date.now()-root.openingStarted;
                    if(elapsed>=250&&elapsed<350){root.expect(Math.abs(left-content.x)>1,"opening used the short closing duration");root.observedLongOpening=true;}
                    if(left<content.x-1){root.observedOvershoot=true;root.expect(left>=0,"spring overshoot is clipped by the window boundary");}
                }
                if(Date.now()<root.deadline)return;
                root.expect(root.observedOvershoot,"spring curve did not overshoot");
                root.expect(root.observedLongOpening,"long opening was not observed");
                root.panel=GlobalFocusGrab.dismissable[0];
                root.expect(root.panel&&root.panel.visible,"sidebar did not open");
                root.expectClickableContent();
                GlobalStates.sidebarRightOpen=false;
                root.expect(root.panel.visible,"sidebar unmapped before slide");
                root.expect(!root.panel.wantsFocus&&!GlobalFocusGrab.dismissable.includes(root.panel),"closing sidebar retained focus grab");
                root.phase=2;root.deadline=Date.now()+100;return;
            }
            if(root.phase===2){
                if(Date.now()<root.deadline)return;
                root.expect(root.panel.visible,"sidebar hidden halfway through exit");
                root.observedClose=true;
                GlobalStates.sidebarRightOpen=true;
                root.expect(GlobalFocusGrab.dismissable.includes(root.panel),"reopen did not restore focus registration");
                root.phase=3;root.deadline=Date.now()+800;return;
            }
            if(root.phase===3){
                if(Date.now()<root.deadline)return;
                root.expect(root.panel.visible,"reopen interrupted incorrectly");
                root.expectClickableContent();
                GlobalStates.sidebarRightOpen=false;
                root.phase=4;root.deadline=Date.now()+350;return;
            }
            if(root.phase===4){
                if(Date.now()<root.deadline)return;
                root.expect(!root.panel.visible&&root.observedClose,"sidebar did not unmap after exit");
                Config.options.appearance.animationSpeed=3;
                GlobalStates.sidebarRightOpen=true;
                root.phase=5;root.deadline=Date.now()+300;return;
            }
            if(root.phase===5){
                if(Date.now()<root.deadline)return;
                GlobalStates.sidebarRightOpen=false;
                root.expect(root.panel.visible,"fast close unmapped immediately");
                root.phase=6;root.deadline=Date.now()+150;return;
            }
            if(Date.now()<root.deadline)return;
            root.expect(!root.panel.visible,"global speed did not accelerate close");
            console.log("SIDEBAR_REVEAL_OK");Qt.quit();
        }catch(error){console.error("SIDEBAR_REVEAL_FAILED",error);Qt.quit();}}
    }
    Timer{interval:8000;running:true;onTriggered:{console.error("SIDEBAR_REVEAL_FAILED timeout");Qt.quit();}}
}''')
            env = dict(os.environ, DOTS_SHELL_SOURCE=str(base), XDG_CONFIG_HOME=str(base / 'config'),
                       XDG_STATE_HOME=str(base / 'state'), XDG_CACHE_HOME=str(base / 'cache'))
            launcher = env.get('DOTS_TEST_LAUNCHER')
            result = subprocess.run([launcher] if launcher else [shutil.which('quickshell'), '-p', str(base)],
                                    env=env, capture_output=True, text=True, timeout=12)
            logs = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, logs)
            self.assertIn('SIDEBAR_REVEAL_OK', logs)
            for error in ('SIDEBAR_REVEAL_FAILED', 'TypeError:', 'ReferenceError:', 'Cannot assign', 'Binding loop', 'Unable to assign'):
                self.assertNotIn(error, logs)
