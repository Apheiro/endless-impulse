"""Real bridge/CLI processes with fake Polkit; no system bus or credentials."""
import json
import os
import select
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

BRIDGE = Path(__file__).resolve().parents[1] / 'src/quickshell/scripts/firewalld/control.py'


class ProcessAuthorizationTests(unittest.TestCase):
    def test_submit_closes_without_reopening_same_prompt(self):
        self.exercise('success', True, 1)

    def test_denied_cancelled_and_accepted_without_retained_permission_stop(self):
        for outcome in ('denied', 'cancelled', 'not-retained'):
            with self.subTest(outcome=outcome):
                self.exercise(outcome, False, 1)

    def test_background_read_never_challenges(self):
        self.exercise('success', False, 0, interactive=False)

    def test_worker_retains_subject_across_refresh_inspection_and_write(self):
        self.exercise('success', True, 1, persistent=True)

    def exercise(self, outcome, complete, challenges, interactive=True, persistent=False):
        with tempfile.TemporaryDirectory(prefix='firewall-identity-') as tmp:
            base = Path(tmp)
            def script(name, body):
                path = base / name
                path.write_text('#!' + sys.executable + '\n' + body)
                path.chmod(0o700)
            common = '''import json,os,sys
from pathlib import Path
base=Path(os.environ['FIXTURE_DIR'])
def event(kind,subject):
 with (base/'events').open('a') as f:f.write(json.dumps({'kind':kind,'subject':subject})+'\\n')
def subject(pid):
 stat=Path('/proc/'+str(pid)+'/stat').read_text().rsplit(')',1)[1].split()[19]
 return str(pid)+','+stat+','+str(os.getuid())
'''
            script('ip', 'print("[]")\n')
            script('nmcli', 'print("")\n')
            script('busctl', 'print(\'s ":fixture"\')\n')
            script('pkcheck', common + '''identity=sys.argv[sys.argv.index('--process')+1]
event('check',identity)
if '--allow-user-interaction' in sys.argv:
 event('challenge',identity)
 outcome=os.environ['FIXTURE_OUTCOME']
 if outcome in ('denied','cancelled'):sys.exit(1 if outcome=='denied' else 3)
 if outcome!='not-retained':(base/identity).touch()
 sys.exit(0)
sys.exit(0 if (base/identity).exists() else 2)
''')
            script('host-python', "import os,sys\nfrom pathlib import Path\nPath(os.environ['FIXTURE_DIR'],'host-interpreter').touch()\nos.execv(sys.executable,[sys.executable,*sys.argv[1:]])\n")
            script('firewall-cmd', common + '''identity=subject(os.getpid())
event('cli',identity)
if not (base/identity).exists():
 # Firewalld's server-side AllowUserInteraction would show another dialog.
 event('challenge',identity)
 print('NOT_AUTHORIZED',file=sys.stderr)
 sys.exit(1)
option=sys.argv[-1]
if option=='--add-service=http':(base/'allowed-http').touch()
if option=='--info-service=http':print('http\\n  ports: 80/tcp');sys.exit(0)
print({'--get-default-zone':'home','--list-all-zones':'home (active)\\n  services: ssh\\n  ports:',
       '--list-all-policies':'','--get-services':'ssh http'}.get(option,'success').replace('services: ssh','services: ssh http' if (base/'allowed-http').exists() else 'services: ssh'))
''')
            cli = base / 'firewall-cmd'
            cli.write_text(cli.read_text().replace('#!' + sys.executable, '#!' + str(base / 'host-python') + ' -u', 1))
            env = dict(os.environ, PATH=tmp + os.pathsep + os.environ['PATH'],
                       FIXTURE_DIR=tmp, FIXTURE_OUTCOME=outcome)
            def attempt(allow):
                return subprocess.run([sys.executable, str(BRIDGE), json.dumps({'action':'snapshot','allowInteraction':allow})],
                                      input='authorize\n', capture_output=True, text=True, env=env, timeout=10)
            if persistent:
                self.exercise_worker(env, base)
                return
            result = attempt(interactive)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((base / 'host-interpreter').exists())
            lines = [json.loads(line) for line in result.stdout.splitlines()]
            state = lines[-1]['snapshot']
            events = [json.loads(line) for line in (base/'events').read_text().splitlines()]
            prompts = [event for event in events if event['kind']=='challenge']
            self.assertEqual(len(prompts), challenges, events)
            self.assertEqual(state['complete'], complete, state)
            self.assertEqual(state['state'], 'connected' if complete else 'access-denied', state)
            if complete:
                calls = [event for event in events if event['kind']=='cli']
                self.assertEqual(len(calls), 9)
                self.assertEqual({event['subject'] for event in calls}, {prompts[0]['subject']})
            else:
                self.assertFalse(any(event['kind']=='cli' for event in events))
                self.assertTrue(state['error'])
            if interactive and not complete:
                # Only an explicit new user attempt may open another challenge.
                env['FIXTURE_OUTCOME'] = 'success'
                retry = attempt(True)
                self.assertTrue(json.loads(retry.stdout.splitlines()[-1])['snapshot']['complete'], retry.stdout)

    def exercise_worker(self, env, base):
        with subprocess.Popen([sys.executable, str(BRIDGE), '--serve'], env=env,
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True) as worker:
            def receive():
                self.assertTrue(select.select([worker.stdout], [], [], 8)[0], 'Worker response timed out')
                line = worker.stdout.readline()
                self.assertTrue(line, 'Worker exited without a response')
                return json.loads(line)
            def send(payload):
                worker.stdin.write(json.dumps(payload) + '\n')
                worker.stdin.flush()
            try:
                self.assertEqual(receive(), {'event': 'ready'})
                send(dict(action='snapshot', allowInteraction=True, requestId=1))
                self.assertEqual(receive(), {'event': 'authorization-required', 'requestId': 1})
                send(dict(event='authorize', requestId=1))
                first = receive()
                self.assertTrue(first['snapshot']['complete'], first)
                send(dict(action='snapshot', allowInteraction=False, requestId=2))
                refresh = receive()
                self.assertEqual(refresh['requestId'], 2)
                self.assertTrue(refresh['snapshot']['complete'], refresh)
                send(dict(action='inspect', kind='service', name='http', scope='runtime', requestId=3))
                detail = receive()
                self.assertEqual(detail['requestId'], 3)
                self.assertEqual(detail['definition']['fields']['ports'], '80/tcp')
                send(dict(action='add-service', zone='home', value='http', scope='runtime', confirmed=True,
                          allowInteraction=True, revision=refresh['snapshot']['revision'], requestId=4))
                applied = receive()
                self.assertEqual(applied['requestId'], 4)
                self.assertEqual(applied['operationState'], 'applied', applied)
                # A bad request is contained to one JSON line; the worker survives.
                send(['invalid request'])
                self.assertFalse(receive()['ok'])
                send(dict(action='snapshot', allowInteraction=False, requestId=5))
                self.assertTrue(receive()['snapshot']['complete'])
                events = [json.loads(line) for line in (base / 'events').read_text().splitlines()]
                prompts = [event for event in events if event['kind'] == 'challenge']
                self.assertEqual(len(prompts), 1, events)
                self.assertEqual({event['subject'] for event in events}, {prompts[0]['subject']})
                worker.stdin.close()
                self.assertEqual(worker.wait(timeout=3), 0)
                self.assertEqual(worker.stderr.read(), '')
            finally:
                if worker.poll() is None:
                    worker.kill()
                    worker.wait(timeout=3)


if __name__ == '__main__':
    unittest.main()
