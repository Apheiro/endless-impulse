"""Global UI timing and its Settings control, using temporary preferences."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/quickshell'


@unittest.skipUnless(os.environ.get('WAYLAND_DISPLAY'), 'Quickshell needs Wayland')
class AnimationSpeedTests(unittest.TestCase):
    def test_global_speed_and_settings_control(self):
        with tempfile.TemporaryDirectory(prefix='ai-animation-speed-') as temporary:
            base = Path(temporary)
            for name in ('modules', 'services', 'assets', 'scripts', 'defaults', 'translations', 'GlobalStates.qml'):
                (base / name).symlink_to(SOURCE / name)
            (base / 'shell.qml').write_text('''//@ pragma UseQApplication
import QtQuick
import Quickshell
import qs.modules.shared
import qs.services
import qs.modules.settings
import qs.modules.windowsStyle.looks
ShellRoot {
    id: root
    property int step: 0
    property var page: null
    property var control: null
    property var sample: null
    property var speeds: [1, 2, 0.25, 3]
    property Component themePage: ThemeConfig { width: 800 }
    function expect(condition, message) { if (!condition) throw new Error(message); }
    function find(item, name) {
        if (item.objectName === name) return item;
        for (const child of item.children || []) { const result = find(child, name); if (result) return result; }
        return null;
    }
    Timer {
        interval: 150; running: true; repeat: true
        onTriggered: { try {
            if (!Config.ready) return;
            if (root.step === 0) {
                const original = Config.options.appearance.animationSpeed;
                root.page = root.themePage.createObject(root);
                root.control = root.find(root.page, "animation-speed-control");
                root.expect(root.control !== null, "missing animation speed setting");
                root.expect(Config.options.appearance.animationSpeed === original, "control saved during initialization");
                root.sample = Appearance.animation.elementMove.numberAnimation.createObject(root);
            }
            if (root.step > root.speeds.length) {
                if (root.step === root.speeds.length + 1) {
                    const editor=root.find(root.page,"animation-duration-move");
                    const compositor=root.find(root.page,"compositor-duration-layersIn");
                    root.expect(editor&&compositor,"individual duration editors did not load");
                    editor.edited(800); compositor.edited(480);
                    Config.options.appearance.animationSpeed=2;
                    root.step++;return;
                }
                root.expect(root.sample.duration===400,"individual duration and multiplier did not combine");
                root.expect(AnimationSpeed.durations.layersIn===480,"compositor duration was not saved");
                root.find(root.page,"animation-duration-move").edited(500);
                root.find(root.page,"compositor-duration-layersIn").edited(270);
                root.expect(Config.options.appearance.animationDurations.move===500,"reset interface duration");
                root.expect(!Object.prototype.hasOwnProperty.call(AnimationSpeed.durations,"layersIn"),"reset did not restore inherited compositor duration");
                console.log("ANIMATION_SPEED_OK");Qt.quit();return;
            }
            if (root.step > 0) {
                const speed = root.speeds[root.step - 1];
                root.expect(Appearance.animationSpeed === speed, "setting did not reach global speed");
                root.expect(root.sample.duration === Math.round(500 / speed), "existing animation did not update");
                root.expect(Appearance.animation.elementMoveFast.duration === Math.round(200 / speed), "fade timing");
                root.expect(Appearance.animation.elementResize.duration === Math.round(300 / speed), "resize timing");
                root.expect(Appearance.animationDuration(220) === Math.round(220 / speed), "custom timing");
                root.expect(Appearance.animation.elementMoveFast.velocity === Math.round(850 * speed), "velocity timing");
                root.expect(Looks.transition.velocity === Math.round(850 * speed), "alternate interface velocity");
                root.expect(Appearance.animationDuration(0) === 0, "zero duration changed");
                root.expect(root.control.value === speed, "setting lost its value binding");
            }
            if (root.step === root.speeds.length) {
                AnimationSpeed.animations=[{name:"layersIn",duration:270,enabled:true}];
                root.find(root.page,"individual-animation-timings").expanded=true;
                root.step++;return;
            }
            root.control.edited(root.speeds[root.step++]);
        } catch (error) { console.error("ANIMATION_SPEED_FAILED", error); Qt.quit(); } }
    }
    Timer { interval: 8000; running: true; onTriggered: { console.error("ANIMATION_SPEED_FAILED timeout"); Qt.quit(); } }
}''')
            env = dict(os.environ, DOTS_SHELL_SOURCE=str(base), XDG_CONFIG_HOME=str(base / 'config'),
                       XDG_STATE_HOME=str(base / 'state'), XDG_CACHE_HOME=str(base / 'cache'))
            launcher = env.get('DOTS_TEST_LAUNCHER')
            result = subprocess.run([launcher] if launcher else [shutil.which('quickshell'), '-p', str(base)],
                                    env=env, capture_output=True, text=True, timeout=12)
            logs = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, logs)
            self.assertIn('ANIMATION_SPEED_OK', logs)
            for error in ('ANIMATION_SPEED_FAILED', 'TypeError:', 'ReferenceError:', 'Cannot assign', 'Binding loop', 'Unable to assign'):
                self.assertNotIn(error, logs)
