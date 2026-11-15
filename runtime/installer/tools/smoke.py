#!/usr/bin/env python3
"""Release-binary, subset and archive smoke. All writes use one private /tmp tree."""
import argparse
import hashlib
import json
import os
import pty
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import select
import termios
import time
import zipfile

CRATE = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, default=CRATE / 'target/release/endless-setup')
    args = parser.parse_args()
    binary = args.binary.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix='endless-release-smoke-', dir='/tmp') as temporary:
        workspace = Path(temporary)
        sandbox = workspace / 'sandbox'
        sandbox.mkdir(mode=0o700)
        fake_home = workspace / 'fake-home'
        fake_home.mkdir(mode=0o700)
        assert workspace.resolve().is_relative_to('/tmp')
        assert not workspace.resolve().is_relative_to(Path.home().resolve())
        environment = dict(os.environ, HOME=str(fake_home))
        bundle = workspace / 'bundle'
        subprocess.run([sys.executable, '-B', str(CRATE / 'tools/build_bundle.py'), '--output', str(bundle)], check=True, capture_output=True, env=environment)
        manifest = bundle / 'manifest.json'
        stages = []

        def run(command, *flags, success=True):
            result = subprocess.run([str(binary), command, '--sandbox', str(sandbox), '--manifest', str(manifest), '--json', *flags], capture_output=True, text=True, timeout=10, env=environment)
            assert (result.returncode == 0) == success, result.stderr
            return json.loads(result.stdout) if success else json.loads(result.stderr)

        for flag in ['--help', '--version']:
            subprocess.run([str(binary), flag], check=True, capture_output=True, timeout=3, env=environment)
        assert run('plan')['completeness'] == 'subset'
        assert len(run('plan')['operations']) == 7
        run('install', '--dry-run')
        run('doctor')
        assert not list(sandbox.iterdir()), 'Preview/doctor wrote state'
        stages.append('plan/dry-run/doctor: no writes')

        # Own pseudo-terminals only, never the user's desktop or terminal.
        def tui_case(confirm):
            root = workspace / ('tui-apply' if confirm else 'tui-cancel')
            root.mkdir(mode=0o700)
            master, slave = pty.openpty()
            original = termios.tcgetattr(slave)
            child = subprocess.Popen([str(binary), 'tui', '--sandbox', str(root), '--manifest', str(manifest)], stdin=slave, stdout=slave, stderr=slave, env=dict(environment, TERM='xterm'))
            transcript = bytearray()

            def until(marker):
                deadline = time.monotonic() + 5
                start = len(transcript)
                while marker not in transcript[start:]:
                    assert time.monotonic() < deadline, f'TUI timed out waiting for {marker!r}'
                    if select.select([master], [], [], 0.05)[0]:
                        transcript.extend(os.read(master, 65536))

            try:
                until(b'Esc: exit')
                # Down/up exercise both directions; two downs select Install.
                os.write(master, b'\x1b[B\x1b[A\x1b[B\x1b[B\r')
                until(b'anything else cancels')
                assert not list(root.iterdir()), 'TUI wrote before confirmation'
                os.write(master, b'APPLY SANDBOX\n' if confirm else b'cancel\n')
                until(b'Esc + Enter: exit')
                os.write(master, b'\x1b\n')
                assert child.wait(timeout=5) == 0
                assert termios.tcgetattr(slave) == original, 'Terminal attributes not restored'
                if confirm:
                    assert (root / '.endless-setup/inventory.json').exists()
                    assert b'subset_applied' in transcript
                else:
                    assert not list(root.iterdir())
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=3)
                os.close(master)
                os.close(slave)

        tui_case(False)
        tui_case(True)
        result = subprocess.run([str(binary), 'tui', '--sandbox', str(sandbox)], stdin=subprocess.DEVNULL, capture_output=True, timeout=3, env=environment)
        assert result.returncode == 0 and not list(sandbox.iterdir())
        stages.append('PTY arrows/Enter/Esc: cancellation, explicit apply and terminal restoration; nonTTY exit')
        assert run('install', '--yes')['status'] == 'subset_applied'
        before = {str(p.relative_to(sandbox)): p.read_bytes() for p in sandbox.rglob('*') if p.is_file()}
        assert run('install', '--yes')['status'] == 'unchanged'
        assert before == {str(p.relative_to(sandbox)): p.read_bytes() for p in sandbox.rglob('*') if p.is_file()}
        stages.append('real 7-file subset + idempotence')
        target = sandbox / 'config/hypr/hyprland/services/shortcuts.lua'
        target.unlink()
        run('repair', '--yes')
        assert target.exists()
        target.write_text('-- disposable personal modification\n')
        run('repair', '--yes', success=False)
        run('uninstall', '--yes')
        assert target.read_text() == '-- disposable personal modification\n'
        assert (sandbox / 'config/hypr/custom/keybinds.lua').exists()
        assert not (sandbox / 'data/icons/illogical-impulse.svg').exists()
        stages.append('repair/conflict/uninstall preserve modified + user files')
        for kind in ['tar.gz', 'zip']:
            output = workspace / f'archive-{kind}'
            subprocess.run([sys.executable, '-B', str(CRATE / 'tools/package_release.py'), '--binary', str(binary), '--bundle', str(bundle), '--output', str(output), '--version', '0.1.0-subset', '--format', kind], check=True, capture_output=True, env=environment)
            archive = next(p for p in output.iterdir() if p.name.endswith('.' + kind))
            expected, filename = (output / 'SHA256SUMS').read_text().strip().split('  ')
            assert filename == archive.name
            assert hashlib.sha256(archive.read_bytes()).hexdigest() == expected
            if kind == 'zip':
                with zipfile.ZipFile(archive) as stream:
                    assert len(stream.namelist()) == 12
                    assert all(not n.startswith('/') and '..' not in n.split('/') for n in stream.namelist())
            else:
                with tarfile.open(archive) as stream:
                    entries = stream.getmembers()
                    assert len(entries) == 12 and all(e.isfile() for e in entries)
                    assert all(not e.name.startswith('/') and '..' not in e.name.split('/') for e in entries)
        stages.append('local tar.gz + ZIP exact entries and SHA256SUMS')
        print(json.dumps({'status': 'PASS', 'stages': stages, 'host_deployment': 'NOT RUN', 'published_releases': False}, indent=2))


if __name__ == '__main__':
    main()
