"""Exercise the real dev script with fake processes, never the user's shell."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DevLauncherTests(unittest.TestCase):
    def restart(self, running=True, build_fails=False):
        with tempfile.TemporaryDirectory(prefix='ai-dev-restart-') as temporary:
            base = Path(temporary)
            checkout = base/'new checkout'
            checkout.mkdir()
            shutil.copy2(ROOT/'dev', checkout/'dev')
            tools = base/'tools'
            tools.mkdir()
            log = base/'commands.jsonl'
            for name in ('nix', 'python3'):
                executable = tools/name
                executable.write_text(f'#!{sys.executable}\n'+'''import json,os,sys
from pathlib import Path
name=Path(sys.argv[0]).name
with Path(os.environ['DEV_TEST_LOG']).open('a') as stream:stream.write(json.dumps([name,*sys.argv[1:]])+'\\n')
if name=='nix' and 'build' in sys.argv and os.environ['DEV_BUILD_FAILS']=='1':sys.exit(2)
if name=='python3' and sys.argv[-1]=='health':sys.exit(0 if os.environ['DEV_RUNNING']=='1' else 1)
if name=='nix' and sys.argv[-1]=='kill':sys.exit(1)
''')
                executable.chmod(0o755)
            env = dict(os.environ, PATH=str(tools)+os.pathsep+os.environ['PATH'],
                       DEV_TEST_LOG=str(log), DEV_RUNNING=str(int(running)), DEV_BUILD_FAILS=str(int(build_fails)))
            result = subprocess.run(['bash', str(checkout/'dev'), 'restart'], env=env, capture_output=True, text=True, timeout=5)
            calls = [json.loads(line) for line in log.read_text().splitlines()]
            return result, calls

    def test_restart_stops_registered_source_and_starts_current_checkout(self):
        result, calls = self.restart()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('build', calls[0])
        self.assertEqual([call[-1] for call in calls[1:3]], ['health', 'stop'])
        self.assertIn('run', calls[-1])
        self.assertIn('--no-duplicate', calls[-1])
        self.assertNotIn('kill', [call[-1] for call in calls])

    def test_restart_without_registered_session_still_launches(self):
        result, calls = self.restart(running=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls[-2][-1], 'kill')
        self.assertIn('--no-duplicate', calls[-1])

    def test_failed_build_does_not_stop_running_desktop(self):
        result, calls = self.restart(build_fails=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(calls), 1)
