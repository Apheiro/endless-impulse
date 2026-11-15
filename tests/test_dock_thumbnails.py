"""Capture an owned test window; verify static caching, sampling, pause and cleanup."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/quickshell'


@unittest.skipUnless(os.environ.get('WAYLAND_DISPLAY'), 'A Wayland compositor is needed for capture')
class DockThumbnailTests(unittest.TestCase):
    def test_real_capture_freezes_samples_and_releases_closed_windows(self):
        with tempfile.TemporaryDirectory(prefix='dock-thumbnail-test-') as directory:
            base = Path(directory)
            for name in ('modules','services','assets','scripts','defaults','translations','GlobalStates.qml'):
                (base / name).symlink_to(SOURCE / name, target_is_directory=(SOURCE / name).is_dir())
            text = '''//@ pragma UseQApplication
import QtQuick
import QtQuick.Window
import Quickshell
import Quickshell.Wayland
import qs.services
import qs.modules.desktop.dock
ShellRoot {
    id: root
    property var target: null
    property int phase: 0
    property double started: 0
    property double initial: 0
    property double stamp: 0
    property int changes: 0
    Window {
        id: sourceWindow
        title: "Endless Impulse thumbnail test"
        visible: true
        width: 320; height: 180
        flags: Qt.Tool | Qt.WindowDoesNotAcceptFocus
        color: "#165cab"
    }
    PanelWindow {
        visible: true
        implicitWidth: 1; implicitHeight: 1
        color: "transparent"
        exclusiveZone: 0
        WlrLayershell.namespace: "quickshell:thumbnail-test"
        WlrLayershell.layer: WlrLayer.Background
        mask: Region {}
        DockPreviewCapture {}
        DockWindowThumbnail { id: thumbnail; toplevel: root.target; sampling: false; minimized: true }
    }
    Timer {
        interval: 100; running: true; repeat: true
        onTriggered: {
            if (root.phase === 0) {
                root.target = ToplevelManager.toplevels.values.find(t => t.title === sourceWindow.title) ?? null;
                if (!root.target || !DockThumbnailCache.key(root.target)) return;
                root.phase = -1;
                DockThumbnailCache.capture(root.target, () => {
                    const frame = DockThumbnailCache.frame(root.target);
                    if (!frame || frame.width > 300 || frame.height > 200) { console.error("THUMBNAIL_FIRST_CAPTURE_FAILED", DockThumbnailCache.hosts.length, DockThumbnailCache.hosts.map(host => host.canCapture), frame?.width, frame?.height, Object.keys(DockThumbnailCache.frames), DockThumbnailCache.key(root.target)); Qt.quit(); return; }
                    frame.grab.saveToFile("__BASE__/first.png");
                    root.initial = frame.requestedAt;
                    root.started = Date.now();
                    sourceWindow.color = "#d92f24";
                    WindowMinimizer.minimize(root.target);
                    root.phase = 1;
                });
            } else if (root.phase === 1 && Date.now() - root.started > 1300) {
                if (!WindowMinimizer.isMinimized(root.target) || DockThumbnailCache.frame(root.target)?.requestedAt !== root.initial) { console.error("THUMBNAIL_CHANGED_WHILE_FROZEN"); Qt.quit(); return; }
                WindowMinimizer.activate(root.target);
                root.phase = 7;
            } else if (root.phase === 7 && !WindowMinimizer.busy && !WindowMinimizer.isMinimized(root.target)) {
                thumbnail.minimized = false;
                thumbnail.sampling = true;
                root.phase = 2;
            } else if (root.phase === 2 && DockThumbnailCache.frame(root.target)?.requestedAt !== root.initial) {
                const frame = DockThumbnailCache.frame(root.target);
                frame.grab.saveToFile("__BASE__/sampled.png");
                root.stamp = frame.requestedAt;
                root.started = Date.now();
                root.phase = 3;
            } else if (root.phase === 3) {
                const frame = DockThumbnailCache.frame(root.target);
                if (frame.requestedAt !== root.stamp) { root.stamp = frame.requestedAt; root.changes++; }
                if (Date.now() - root.started < 2400) return;
                if (root.changes < 1 || root.changes > 3) { console.error("THUMBNAIL_RATE_FAILED", root.changes); Qt.quit(); return; }
                thumbnail.sampling = false;
                root.started = Date.now(); root.phase = 4;
            } else if (root.phase === 4 && Date.now() - root.started > 500) {
                root.stamp = DockThumbnailCache.frame(root.target).requestedAt;
                root.started = Date.now(); root.phase = 5;
            } else if (root.phase === 5 && Date.now() - root.started > 1300) {
                if (DockThumbnailCache.frame(root.target).requestedAt !== root.stamp) { console.error("THUMBNAIL_CAPTURED_WHILE_HIDDEN"); Qt.quit(); return; }
                sourceWindow.visible = false;
                root.phase = 6;
            } else if (root.phase === 6 && Object.keys(DockThumbnailCache.frames).length === 0) {
                console.log("THUMBNAIL_CACHE_OK", root.changes);
                Qt.quit();
            }
        }
    }
    Timer { interval: 15000; running: true; onTriggered: { console.error("THUMBNAIL_TIMEOUT", root.phase); Qt.quit(); } }
}
'''.replace('__BASE__', str(base))
            (base / 'shell.qml').write_text(text)
            env = dict(os.environ, AI_THUMBNAIL_DEBUG="1", DOTS_SHELL_SOURCE=str(base), XDG_CONFIG_HOME=str(base/'config'),
                       XDG_STATE_HOME=str(base/'state'), XDG_CACHE_HOME=str(base/'cache'))
            launcher = env.get('DOTS_TEST_LAUNCHER')
            command = [launcher] if launcher else [shutil.which('quickshell'), '-p', str(base)]
            result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=20)
            logs = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, logs)
            self.assertIn('THUMBNAIL_CACHE_OK', logs)
            self.assertNotIn('TypeError:', logs)
            self.assertNotIn('ReferenceError:', logs)
            from PIL import Image
            for name, color in [('first.png',(22,92,171)),('sampled.png',(217,47,36))]:
                with Image.open(base/name).convert('RGB') as frame:
                    self.assertLessEqual(frame.width, 300)
                    self.assertLessEqual(frame.height, 200)
                    pixel = frame.getpixel((frame.width//2, frame.height//2))
                    # Hyprland's current opacity/color settings affect captured RGB.
                    # Check the fixture's hue and the blue -> red transition instead.
                    dominant = max(range(3), key=lambda channel: color[channel])
                    others = [pixel[channel] for channel in range(3) if channel != dominant]
                    self.assertGreater(pixel[dominant], max(others) * 1.25, (name,pixel,color))
