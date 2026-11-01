"""UI reconciliation and activity indicator without writing to the user's audio devices."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'src/quickshell'

@unittest.skipUnless(os.environ.get('WAYLAND_DISPLAY'),'Audio controls need Wayland')
class AudioControlsTests(unittest.TestCase):
    def test_pending_volumes_ignore_stale_snapshots_and_button_stays_centered(self):
        with tempfile.TemporaryDirectory(prefix='ai-audio-controls-') as temporary:
            base=Path(temporary)
            for name in ('modules','services','assets','scripts','defaults','translations','GlobalStates.qml'):
                (base/name).symlink_to(SOURCE/name,target_is_directory=(SOURCE/name).is_dir())
            (base/'shell.qml').write_text('''//@ pragma UseQApplication
import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Wayland
import qs.services
import qs.modules.shared
import qs.modules.desktop.audio
ShellRoot {
    id:root
    property int phase:0
    property bool bell:false
    property real pulseScale:0
    property var first:({action:"volume",kind:"sink",id:"test",serial:"test",value:70})
    property var next:({action:"volume",kind:"sink",id:"test",serial:"test",value:85})
    property var oldEntry:({kind:"sink",id:"test",serial:"test",volume:30,channels:[{volume:30},{volume:30}]})
    function expect(condition, message) {if(!condition)throw new Error(message);}
    function find(item, name) {if(item.objectName===name)return item;for(const child of item.children||[]){const match=find(child,name);if(match)return match;}return null;}
    PanelWindow {
        id:host
        implicitWidth:250;implicitHeight:55;exclusiveZone:0
        WlrLayershell.namespace:"quickshell:audio-controls-test"
        WlrLayershell.keyboardFocus:WlrKeyboardFocus.None
        mask:Region{}
        RowLayout {
            anchors.centerIn:parent
            layoutDirection:Qt.LeftToRight
            Rectangle{id:notification;visible:root.bell;implicitWidth:20;implicitHeight:20;color:Appearance.colors.colPrimary}
            AudioPanelButton{id:button}
            AudioRefreshButton{id:refresh}
        }
    }
    Timer {
        interval:120;running:true;repeat:true
        onTriggered:{
            try {
                const glyph=root.find(button,"audio-button-glyph");
                const point=glyph.mapToItem(button,glyph.width/2,glyph.height/2);
                root.expect(Math.abs(point.x-button.width/2)<1 && Math.abs(point.y-button.height/2)<1,"GLYPH_NOT_CENTERED");
                root.expect(refresh.enabled && refresh.opacity===1,"REFRESH_FLICKER");
                if(root.phase===0){
                    AudioControl.rememberVolume(root.first);
                    AudioControl.reconcileVolumes({sink:[root.oldEntry]},0);
                    root.expect(AudioControl.previewVolume(root.oldEntry,-1)===70,"STALE_SNAPSHOT_ROLLBACK");
                    AudioControl.acknowledgeVolume(root.first,true);
                    AudioControl.reconcileVolumes({sink:[root.oldEntry]},root.first.revision);
                    root.expect(AudioControl.previewVolume(root.oldEntry,-1)===70,"LATE_BACKEND_ROLLBACK");
                    AudioControl.rememberVolume(root.next);
                    const older=Object.assign({},root.oldEntry,{volume:70,channels:[{volume:70},{volume:70}]});
                    AudioControl.acknowledgeVolume(root.first,true);
                    AudioControl.reconcileVolumes({sink:[older]},root.first.revision);
                    root.expect(AudioControl.previewVolume(root.oldEntry,-1)===85,"NEWER_REQUEST_OVERWRITTEN");
                    AudioControl.acknowledgeVolume(root.next,true);
                    const latest=Object.assign({},root.oldEntry,{volume:85,channels:[{volume:85},{volume:85}]});
                    AudioControl.reconcileVolumes({sink:[latest]},root.next.revision);
                    root.expect(Object.keys(AudioControl.pendingVolumes).length===0,"CONFIRMATION_NOT_CLEARED");
                    const failed=Object.assign({},root.first,{value:90});
                    AudioControl.rememberVolume(failed);AudioControl.acknowledgeVolume(failed,false);
                    root.expect(AudioControl.previewVolume(root.oldEntry,-1)===30,"FAILURE_NOT_RESTORED");
                    root.bell=true;
                    AudioControl.open();
                }else if(root.phase===1){
                    root.expect(notification.x+notification.width<=button.x,"NOTIFICATION_REORDERS_SOUND");
                    const pulse=root.find(refresh,"audio-refresh-pulse");
                    root.expect(pulse.opacity>0,"REFRESH_ACTIVITY_NOT_VISIBLE");
                    root.pulseScale=pulse.scale;
                    AudioControl.refresh();
                }else{
                    const pulse=root.find(refresh,"audio-refresh-pulse");
                    root.expect(Math.abs(root.pulseScale-pulse.scale)>0.001,"REFRESH_ACTIVITY_NOT_ANIMATED");
                    AudioControl.close();console.log("AUDIO_CONTROLS_OK");Qt.quit();
                }
                root.phase++;
            } catch(error){console.error("AUDIO_CONTROLS_FAILED",error);Qt.quit();}
        }
    }
}''')
            env=dict(os.environ,DOTS_SHELL_SOURCE=str(base),XDG_CONFIG_HOME=str(base/'config'),XDG_STATE_HOME=str(base/'state'),XDG_CACHE_HOME=str(base/'cache'))
            launcher=env.get('DOTS_TEST_LAUNCHER')
            command=[launcher] if launcher else [shutil.which('quickshell'),'-p',str(base)]
            result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=10)
            logs=result.stdout+result.stderr
            self.assertEqual(result.returncode,0,logs)
            self.assertIn('AUDIO_CONTROLS_OK',logs)
            for failure in ('TypeError:','ReferenceError:','Cannot assign','Binding loop','Unable to assign'):
                self.assertNotIn(failure,logs)
