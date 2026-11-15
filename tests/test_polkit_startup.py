"""Startup guard checks; never launch an agent or change session services."""
import fcntl
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'config/xdg/config/hypr/hyprland/scripts/start_polkit_agent.sh'


class PolkitStartupTests(unittest.TestCase):
    def test_fallback_is_explicit_and_cannot_compete_with_native_host(self):
        with tempfile.TemporaryDirectory(prefix='polkit-fallback-') as tmp:
            env = dict(os.environ, XDG_RUNTIME_DIR=tmp, HYPRLAND_INSTANCE_SIGNATURE='fixture')
            result = subprocess.run(['bash', str(HELPER)], env=env, capture_output=True, timeout=3)
            self.assertEqual(result.returncode, 2)
            directory = Path(tmp) / ('ai-auth-' + hashlib.sha256(b'fixture').hexdigest()[:16])
            directory.mkdir(mode=0o700)
            with (directory / 'owner.lock').open('w') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                result = subprocess.run(['bash', str(HELPER), '--fallback'], env=env,
                                        capture_output=True, timeout=3)
                self.assertEqual(result.returncode, 1)
                self.assertIn(b'Native authentication host is running', result.stderr)

    def test_native_presentation_is_outside_layout_loaders(self):
        source = ROOT / 'src/quickshell'
        self.assertEqual((source / 'shell.qml').read_text().count('component: PolkitPanel {}'), 1)
        for layout in ('DesktopShell', 'WindowsStyleShell'):
            self.assertNotIn('component: Polkit', (source / 'shellVariants' / (layout+'.qml')).read_text())
            self.assertNotIn('component: WafflePolkit', (source / 'shellVariants' / (layout+'.qml')).read_text())
        for name in ('config/xdg/config/hypr/hyprland/execs.lua', 'config/variants/fedora/hypr/hyprland/execs.conf', 'installer/commands/install/3.files-legacy.sh'):
            for line in (ROOT / name).read_text().splitlines():
                if line.strip().startswith(('#', '--')): continue
                self.assertNotIn('start_polkit_agent.sh', line)
                self.assertNotIn('polkit-kde-authentication-agent-1', line)

    def test_existing_agent_is_respected_and_lock_prevents_duplicate_start(self):
        with tempfile.TemporaryDirectory(prefix='polkit-startup-') as tmp:
            base = Path(tmp)
            marker = base / 'checked'
            # A positive process check guarantees the real helper exits before
            # reaching any installed agent. All writes stay in this fixture.
            pgrep = base / 'pgrep'
            pgrep.write_text('#!/bin/sh\ntouch "$XDG_RUNTIME_DIR/checked"\nexit 0\n')
            pgrep.chmod(0o700)
            env = dict(os.environ, PATH=tmp + ':' + os.environ['PATH'], XDG_RUNTIME_DIR=tmp)
            result = subprocess.run(['bash', str(HELPER), '--fallback'], env=env, capture_output=True, timeout=3)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(marker.exists())
            marker.unlink()
            with (base / 'endless-Impulse-polkit-agent.lock').open('w') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                result = subprocess.run(['bash', str(HELPER), '--fallback'], env=env, capture_output=True, timeout=3)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse(marker.exists())


if __name__ == '__main__':
    unittest.main()
