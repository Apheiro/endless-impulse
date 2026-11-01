"""Record only an owned solid-color fixture, with isolated preferences and no audio."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'src/quickshell'


@unittest.skipUnless(os.environ.get('WAYLAND_DISPLAY') and Path('/usr/bin/gpu-screen-recorder').exists(), 'Native GPU Screen Recorder and Wayland are needed')
class RecorderCaptureTests(unittest.TestCase):
    def test_real_region_capture_pause_resume_overlay_and_finalized_video(self):
        with tempfile.TemporaryDirectory(prefix='ai-recorder-test-') as temporary:
            base = Path(temporary)
            for name in ('modules','services','assets','scripts','defaults','translations','GlobalStates.qml'):
                (base/name).symlink_to(SOURCE/name, target_is_directory=(SOURCE/name).is_dir())
            config = base/'config/artificial-impulse'
            config.mkdir(parents=True)
            (config/'recorder.json').write_text(json.dumps(dict(saveDirectory=str(base/'videos'),filenamePattern='fixture_%Y-%m-%d_%H-%M-%S',container='mkv',fps=24,codec='h264',audioTracks=[],cursor=False)))
            fixture = '''//@ pragma UseQApplication
import QtQuick
import QtQuick.Window
import Quickshell
import Quickshell.Wayland
import Quickshell.Io
import qs.services
import qs.modules.desktop.recording
import qs.modules.desktop.bar
ShellRoot {
    id: root
    property int phase: 0
    property double stamp: 0
    property int pausedTime: 0
    RecordingOverlay {}
    Process {
        id: externalStart
        property var region
        stdinEnabled: true
        command: ["python3", Quickshell.shellPath("scripts/videos/recorder.py"), "start"]
        onStarted: { write(JSON.stringify({target:"region",region:region})); stdinEnabled=false; }
        stdout: StdioCollector {}
        stderr: StdioCollector {}
    }
    Window {
        id: fixture
        visible: true; width: 480; height: 300
        title: "Artificial Impulse recorder fixture"
        flags: Qt.Tool | Qt.WindowDoesNotAcceptFocus
        color: "#165cab"
    }
    PanelWindow {
        implicitWidth: 1; implicitHeight: 1; visible: true; color: "transparent"
        WlrLayershell.namespace: "quickshell:recorder-test-host"
        WlrLayershell.layer: WlrLayer.Background
        exclusiveZone: 0; mask: Region {}
        RecordingButton {}
        RecordingIndicator {}
    }
    Timer {
        interval: 100; running: true; repeat: true
        onTriggered: {
            if (ScreenRecorder.failed) { console.error("RECORDER_FAILED", ScreenRecorder.message); ScreenRecorder.stop(); Qt.quit(); return; }
            if (!ScreenRecorder.loaded || ScreenRecorder.busy) return;
            if (root.phase === 0) {
                const window = HyprlandData.windowList.find(w => w.title === fixture.title);
                if (!window || !window.at || window.size[0] < 200) return;
                root.phase++;
                externalStart.region={x:window.at[0]+40,y:window.at[1]+40,width:224,height:160}; externalStart.running=true;
            } else if (root.phase === 1 && ScreenRecorder.recording && ScreenRecorder.elapsed >= 1) {
                if (!ScreenRecorder.state.region?.monitor) { console.error("RECORDER_REGION_MISSING"); Qt.quit(); return; }
                ScreenRecorder.pause(); root.phase++;
            } else if (root.phase === 2 && ScreenRecorder.paused) {
                root.stamp = Date.now(); root.pausedTime = ScreenRecorder.elapsed; root.phase++;
            } else if (root.phase === 3 && Date.now()-root.stamp>900) {
                if (ScreenRecorder.elapsed !== root.pausedTime) { console.error("RECORDER_PAUSE_TIMER_FAILED",ScreenRecorder.elapsed,root.pausedTime); ScreenRecorder.stop(); Qt.quit(); return; }
                ScreenRecorder.pause(); root.phase++;
            } else if (root.phase === 4 && !ScreenRecorder.paused && ScreenRecorder.elapsed >= 2) {
                ScreenRecorder.stop(); root.phase++;
            } else if (root.phase === 5 && !ScreenRecorder.active) {
                if (!ScreenRecorder.state.lastSaved || ScreenRecorder.state.exitCode !== 0) { console.error("RECORDER_SAVE_FAILED",JSON.stringify(ScreenRecorder.state)); Qt.quit(); return; }
                console.log("RECORDER_CAPTURE_OK",ScreenRecorder.state.lastSaved); Qt.quit();
            }
        }
    }
    Timer { interval:25000; running:true; onTriggered:{ console.error("RECORDER_TIMEOUT",root.phase,JSON.stringify(ScreenRecorder.state)); ScreenRecorder.stop(); Qt.quit(); } }
}'''
            (base/'shell.qml').write_text(fixture)
            environment = dict(os.environ,DOTS_SHELL_SOURCE=str(base),XDG_CONFIG_HOME=str(base/'config'),XDG_STATE_HOME=str(base/'state'),XDG_CACHE_HOME=str(base/'cache'),DOTS_GSR_BINARY='/usr/bin/gpu-screen-recorder')
            launcher = environment.get('DOTS_TEST_LAUNCHER')
            command = [launcher] if launcher else [shutil.which('quickshell'),'-p',str(base)]
            try:
                result = subprocess.run(command,env=environment,capture_output=True,text=True,timeout=30)
                logs=result.stdout+result.stderr
                (ROOT/'work/recorder-real-ui.log').write_text(logs)
                self.assertEqual(result.returncode,0,logs)
                self.assertIn('RECORDER_CAPTURE_OK',logs)
                self.assertNotIn('TypeError:',logs)
                self.assertNotIn('ReferenceError:',logs)
                self.assertNotIn('Cannot assign',logs)
                videos=list((base/'videos').glob('*.mkv'))
                self.assertEqual(len(videos),1,logs)
                probe=subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(videos[0])],capture_output=True,text=True,check=True)
                metadata=json.loads(probe.stdout)
                video=next(s for s in metadata['streams'] if s['codec_type']=='video')
                self.assertEqual((video['width'],video['height']),(224,160))
                self.assertGreater(float(metadata['format']['duration']),1)
                subprocess.run(['ffmpeg','-v','error','-i',str(videos[0]),'-frames:v','1',str(base/'frame.png')],check=True,capture_output=True)
                from PIL import Image
                with Image.open(base/'frame.png').convert('RGB') as frame:
                    pixel=frame.getpixel((112,80))
                    # Compositor opacity/color management can alter exact RGB values.
                    self.assertTrue(pixel[2] > 100 and pixel[2] > pixel[0]*3 and pixel[1] > pixel[0]*1.5, pixel)
                    edge=frame.getpixel((1,1))
                    self.assertGreater(edge[2],edge[0]*2,edge)
            finally:
                state_folder=base/'state/artificial-impulse/recorder'
                if state_folder.exists():
                    for name in ('session.json','recording.log','supervisor.log'):
                        if (state_folder/name).exists(): (ROOT/'work'/('recorder-'+name)).write_bytes((state_folder/name).read_bytes())
                subprocess.run(['python3',str(SOURCE/'scripts/videos/recorder.py'),'stop'],env=environment,capture_output=True,timeout=25)
