"""Regression for the recorder pill, clock layout and popup item anchor."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'src/quickshell'


@unittest.skipUnless(os.environ.get('WAYLAND_DISPLAY'), 'The recording bar needs Wayland')
class RecordingBarTests(unittest.TestCase):
    def test_pill_keeps_clock_width_and_popup_anchor_after_resize(self):
        with tempfile.TemporaryDirectory(prefix='ai-recording-bar-') as temporary:
            base=Path(temporary)
            for name in ('modules','services','assets','scripts','defaults','translations','GlobalStates.qml'):
                (base/name).symlink_to(SOURCE/name,target_is_directory=(SOURCE/name).is_dir())
            text='''//@ pragma UseQApplication
import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Wayland
import qs.services
import qs.modules.shared
import qs.modules.desktop.bar
ShellRoot {
    id: root
    property int phase: 0
    property real clockWidth: 0
    property real idleWidth: 0
    PanelWindow {
        id: host
        visible: true; implicitWidth: 800; implicitHeight: 60
        color: Appearance.colors.colLayer0
        exclusiveZone: 0
        WlrLayershell.namespace: "quickshell:recording-bar-test"
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
        mask: Region {}
        RowLayout {
            id: recordingRow
            anchors.centerIn: parent
            spacing: 12
            ClockWidget { id: clock; showDate: true; Layout.minimumWidth: implicitWidth }
            RecordingButton { id: button; Layout.minimumWidth: implicitWidth }
        }
    }
    Timer {
        interval: 120; running: true; repeat: true
        onTriggered: {
            if (!ScreenRecorder.loaded || ScreenRecorder.busy) return;
            if (root.phase === 0) {
                root.clockWidth=clock.implicitWidth; root.idleWidth=button.implicitWidth;
                ScreenRecorder.state={active:true,phase:"recording",elapsed:125,mode:"record"};
                root.phase++;
            } else if (root.phase === 1) {
                if (clock.implicitWidth !== root.clockWidth || button.implicitWidth <= root.idleWidth || clock.x+clock.width > button.x) {
                    console.error("RECORDING_LAYOUT_FAILED",clock.implicitWidth,root.clockWidth,button.implicitWidth,root.idleWidth); Qt.quit(); return;
                }
                button.toggleMenu(); root.phase++;
            } else if (root.phase === 2) {
                if (!button.contextMenu.visible || button.contextMenu.anchor.item !== button || button.contextMenu.anchor.gravity !== Edges.Bottom) {
                    console.error("RECORDING_ANCHOR_FAILED"); Qt.quit(); return;
                }
                const surface=button.contextMenu.contentItem.children.find(child => child.objectName === "recording-menu-surface");
                if (!surface || String(surface.color) !== String(Appearance.colors.colLayer0) || surface.color.a < 0.5 || surface.anchors.leftMargin <= 0) {
                    console.error("RECORDING_MENU_SURFACE_FAILED",surface?.color); Qt.quit(); return;
                }
                button.toggleMenu();
                const output=Quickshell.env("DOTS_TEST_RECORDING_BAR_IMAGE");
                if (output) recordingRow.grabToImage(result => { result.saveToFile(output); ScreenRecorder.state={active:false,phase:"idle"}; });
                else ScreenRecorder.state={active:false,phase:"idle"};
                root.phase++;
            } else {
                if (button.implicitWidth !== root.idleWidth || clock.implicitWidth !== root.clockWidth) {
                    console.error("RECORDING_RESTORE_FAILED"); Qt.quit(); return;
                }
                console.log("RECORDING_BAR_OK"); Qt.quit();
            }
        }
    }
    Timer { interval: 10000; running: true; onTriggered: { console.error("RECORDING_BAR_TIMEOUT",root.phase); Qt.quit(); } }
}'''
            (base/'shell.qml').write_text(text)
            env=dict(os.environ,DOTS_SHELL_SOURCE=str(base),XDG_CONFIG_HOME=str(base/'config'),XDG_STATE_HOME=str(base/'state'),XDG_CACHE_HOME=str(base/'cache'))
            launcher=env.get('DOTS_TEST_LAUNCHER')
            command=[launcher] if launcher else [shutil.which('quickshell'),'-p',str(base)]
            result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=15)
            logs=result.stdout+result.stderr
            self.assertEqual(result.returncode,0,logs)
            self.assertIn('RECORDING_BAR_OK',logs)
            for failure in ('TypeError:','ReferenceError:','Cannot assign','Binding loop'):
                self.assertNotIn(failure,logs)
