"""Tailscale bridge tests: all commands use a disposable simulated executable."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('tailscale_control', ROOT / 'src/quickshell/scripts/tailscale/control.py')
ts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ts)

FAKE = '''#!/usr/bin/env python3
import sys,json,time,os
args=sys.argv[1:]
state_path = os.environ.get('TAILSCALE_TEST_STATE')
state = {'running':True, 'hostname':'custom-device', 'operator':'saved-operator'}
if state_path and os.path.exists(state_path):
 with open(state_path) as saved: state = json.load(saved)
if os.environ.get('TAILSCALE_TEST_CALLS'):
 with open(os.environ['TAILSCALE_TEST_CALLS'],'a') as log: log.write(json.dumps(args)+'\\n')
if '--help' in args:
 if args == ['--help']:
  print('SUBCOMMANDS\\n  up  Connect\\n  down  Disconnect\\n  set  Preferences\\n  switch  Accounts\\n  ping  Ping\\n  login  Login\\n  debug  Diagnostics')
 else:
  print('USAGE\\n  tailscale '+args[0]+' <target>\\nFLAGS\\n  --enabled, --enabled=false\\n    switch\\n  --auth-key value\\n    secret\\n  --hostname value\\n    name\\n  --accept-dns, --accept-dns=false\\n    Use DNS\\n  --accept-routes, --accept-routes=false\\n    Use subnet routes\\n  --shields-up, --shields-up=false\\n    Block inbound\\n  --ssh, --ssh=false\\n    Tailscale SSH\\n  --webclient, --webclient=false\\n    Web interface\\n  --exit-node-allow-lan-access, --exit-node-allow-lan-access=false\\n    Local network\\n  --advertise-exit-node, --advertise-exit-node=false\\n    Share exit\\n  --advertise-routes value\\n    Shared networks\\n  --timeout value\\n    maximum time to wait')
elif args[:1] == ['status']:
 print(json.dumps({'BackendState':'Running' if state['running'] else 'Stopped','Self':{'HostName':'fake'},'Peer':{'peer':{'ID':'peer','HostName':'peer','TailscaleIPs':['100.64.0.2'],'Online':True,'ExitNodeOption':True}},'TailscaleIPs':['100.64.0.1']}))
elif args[:2] == ['switch','--list']:
 print(json.dumps([{'id':'saved','nickname':'Test','selected':True}]))
elif args[:2] == ['debug','prefs']:
 print(json.dumps({'CorpDNS':True,'Persist':{'PrivateNodeKey':'PRIVATE'},'PrivateKey':'PRIVATE','Hostname':state['hostname'],'OperatorUser':state['operator']}))
elif args[:1] in (['up'], ['down']):
 if args[0] == 'up' and len(args) > 1:
  print('Error: changing settings via tailscale up requires mentioning all non-default flags', file=sys.stderr)
  sys.exit(1)
 state['running'] = args[0] == 'up'
 if state_path:
  with open(state_path,'w') as saved: json.dump(state,saved)
elif args[:1] == ['ping']:
 print('started',flush=True)
 time.sleep(60)
else:
 print('tskey-auth-EXAMPLE privkey:deadbeef')
'''

class TailscaleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.binary = Path(self.tmp.name) / 'tailscale'
        self.binary.write_text(FAKE)
        self.binary.chmod(0o755)
        self.client = ts.Tailscale(str(self.binary))

    def test_snapshot_filters_private_preferences_and_preserves_accounts(self):
        state = self.client.snapshot()
        self.assertTrue(state['running'])
        self.assertEqual(state['profiles'][0]['id'], 'saved')
        self.assertTrue(state['prefs']['accept-dns'])
        self.assertNotIn('PRIVATE', json.dumps(state))
        self.assertNotIn('Persist', json.dumps(state))

    def test_schema_and_argument_boundaries(self):
        schema = self.client.schema(['set'])
        self.assertEqual(schema['flags'][0]['type'], 'bool')
        self.assertTrue(schema['flags'][1]['secret'])
        command = self.client.command(['set'], {'enabled':False,'hostname':'$(touch /tmp/never)'}, ['--auth-key=hostile'])
        self.assertEqual(command[-2:], ['--','--auth-key=hostile'])
        self.assertIn('--hostname=$(touch /tmp/never)',command)
        self.assertIn('--enabled=false',command)
        for path,flags,args in [(['invalid'],{},[]),(['set'],{'invalid':'x'},[]),(['set'],{'enabled':'false'},[]),(['set'],{},['\0'])]:
            with self.assertRaises(ValueError): self.client.command(path,flags,args)

    def test_reconnect_preserves_non_default_preferences(self):
        state_path = Path(self.tmp.name) / 'saved-state.json'
        initial = {'running':True, 'hostname':'custom-device', 'operator':'saved-operator'}
        state_path.write_text(json.dumps(initial))
        controller = ts.Controller(self.client)
        events = []
        controller.emit = lambda **event: events.append(event)
        with patch.dict(os.environ, TAILSCALE_TEST_STATE=str(state_path)):
            controller.handle({'action':'run','path':['down']})
            self.assertTrue(events[-1]['ok'])
            self.assertFalse(self.client.snapshot()['running'])
            # Reproduce the CLI's rejection of the previous reconnect command.
            controller.handle({'action':'run','path':['up'],'flags':{'timeout':'10s'}})
            self.assertFalse(events[-1]['ok'])
            self.assertFalse(self.client.snapshot()['running'])
            controller.handle({'action':'run','path':['up']})
            self.assertTrue(events[-1]['ok'])
            self.assertTrue(self.client.snapshot()['running'])
        self.assertEqual(json.loads(state_path.read_text()), initial)

    def test_redaction(self):
        text = ts.redact('tskey-auth-ABC privkey:1234 "PrivateNodeKey": "private" password=hidden exact', ['exact'])
        for secret in ['tskey-auth-ABC','privkey:1234','private','hidden','exact']:
            self.assertNotIn(secret,text)

    def test_cancel_reaps_simulated_operation(self):
        controller = ts.Controller(self.client)
        events = []
        controller.emit = lambda **event: events.append(event)
        thread = threading.Thread(target=controller.handle,args=({'action':'run','path':['ping'],'args':['fake']},))
        thread.start()
        deadline = time.monotonic()+5
        while not any(e.get('text') == 'started\n' for e in events) and time.monotonic() < deadline:
            time.sleep(.01)
        controller.cancel()
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertIsNone(controller.process)
        self.assertFalse(events[-1]['ok'])

    def test_output_is_redacted(self):
        controller = ts.Controller(self.client)
        events=[]
        controller.emit=lambda **event: events.append(event)
        controller.handle({'action':'run','path':['set'],'flags':{},'args':[]})
        self.assertNotIn('tskey-auth-EXAMPLE',json.dumps(events))
        self.assertTrue(events[-1]['ok'])

    def test_numeric_schema_preserves_units_and_bounds(self):
        schema = ts.parse_help('FLAGS\n  --https value\n    HTTPS port\n  --timeout value\n    duration (default 5s)', ['serve'])
        self.assertEqual(schema['flags'][0]['maximum'], 65535)
        self.assertEqual(schema['flags'][0]['minimum'], 1)
        self.assertNotIn('input', schema['flags'][1])
        self.assertIn('5s', schema['flags'][1]['description'])

    def test_worker_shutdown_stops_managed_child(self):
        import subprocess
        import sys
        for terminate in (False, True):
            with self.subTest(terminate=terminate):
                env = dict(os.environ, DOTS_TAILSCALE_BINARY=str(self.binary))
                bridge = subprocess.Popen([sys.executable, str(ROOT/'src/quickshell/scripts/tailscale/control.py')],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
                try:
                    bridge.stdin.write(json.dumps({'action':'run','path':['ping'],'args':['fake']})+'\n')
                    bridge.stdin.flush()
                    self.assertEqual(json.loads(bridge.stdout.readline())['event'], 'running')
                    self.assertEqual(json.loads(bridge.stdout.readline())['event'], 'output')
                    if terminate: bridge.terminate()
                    else:
                        bridge.stdin.close()
                        bridge.stdin = None
                    stdout, stderr = bridge.communicate(timeout=7)
                    self.assertEqual(bridge.returncode, 0, stderr)
                    self.assertNotIn('Traceback', stderr)
                finally:
                    if bridge.poll() is None:
                        bridge.kill()
                        bridge.communicate()

    def test_missing_binary_and_shutdown(self):
        with patch.object(ts,'executable',return_value=None):
            self.assertFalse(ts.Tailscale().snapshot()['installed'])
        controller=ts.Controller(self.client)
        controller.stopping=True
        with self.assertRaises(ValueError): controller.run({'path':['set']})

@unittest.skipUnless(os.environ.get("WAYLAND_DISPLAY"), "Quickshell needs Wayland")
class TailscaleQmlTests(unittest.TestCase):
    def test_views_load_with_simulated_service(self):
        import shutil
        import subprocess
        source = ROOT / 'src/quickshell'
        with tempfile.TemporaryDirectory(prefix='tailscale-ui-') as directory:
            base = Path(directory)
            for name in ('modules', 'services', 'assets', 'scripts', 'defaults', 'translations', 'GlobalStates.qml'):
                (base / name).symlink_to(source / name, target_is_directory=(source / name).is_dir())
            binary = base / 'tailscale'
            binary.write_text(FAKE)
            binary.chmod(0o755)
            (base / 'shell.qml').write_text("""//@ pragma UseQApplication
import QtQuick
import Quickshell
import qs.services
import qs.modules.desktop.tailscale
import qs.modules.desktop.sidebarRight.quickToggles.androidStyle
import qs.modules.desktop.sidebarRight.quickToggles.classicStyle as Classic
ShellRoot {
    TailscaleWindow { id: actualWindow; visible: false }
    PanelWindow {
        visible: false
        Item {
            width: 800; height: 600
            AndroidTailscaleToggle {
                id: quick
                buttonData: ({type: "tailscale", size: 2})
                expandedSize: true
                baseCellWidth: 70; baseCellHeight: 56; cellSpacing: 8; cellSize: 2
            }
            Classic.Tailscale { id: classic }
            TailscaleConnections { width: 800 }
            TailscaleDevices { width: 800 }
            TailscalePreferences { width: 800 }
            TailscaleCommandBrowser { id: browser; width: 800 }
        }
    }
    Timer {
        interval: 100; running: true; repeat: true
        property int phase: 0
        property int openTicks: 0
        onTriggered: {
            if (TailscaleControl.loaded && !TailscaleControl.schemaLoading) {
                if (actualWindow.tab < 3) { actualWindow.tab++; return; }
                if (TailscaleControl.commandPath.length === 0) {
                    TailscaleControl.selectCommand(["set"]); return;
                }
                if (phase === 0) {
                    if (quick.iconSource !== "tailscale-symbolic.svg" || classic.iconSource !== quick.iconSource) { console.error("WRONG_TAILSCALE_ICON"); Qt.quit(); return; }
                    quick.clicked(); phase++; return;
                }
                if (TailscaleControl.busy) return;
                if (phase === 1) {
                    quick.altAction();
                    if (!TailscaleControl.opened) { console.error("MENU_DID_NOT_OPEN"); Qt.quit(); return; }
                    GlobalFocusGrab.dismiss();
                    if (!TailscaleControl.opened) { console.error("GLOBAL_MENU_CLOSED_TAILSCALE"); Qt.quit(); return; }
                    classic.clicked(); phase++; return;
                }
                if (phase === 2) {
                    if (!TailscaleControl.state.running || TailscaleControl.error) { console.error("RECONNECT_FAILED", TailscaleControl.error); Qt.quit(); return; }
                    browser.setOption("enabled", true, true);
                    browser.setOption("hostname", "example", true);
                    phase++; return;
                }
                if (browser.flags.enabled !== true || browser.flags.hostname !== "example") { console.error("OPTION_VALUES_CHANGED"); Qt.quit(); return; }
                if (!TailscaleControl.opened) { console.error("PANEL_CLOSED_DURING_REFRESH"); Qt.quit(); return; }
                // Cross the open panel's three-second polling interval.
                if (++openTicks < 35) return;
                TailscaleControl.close();
                if (TailscaleControl.opened) { console.error("EXPLICIT_CLOSE_FAILED"); Qt.quit(); return; }
                console.log("TAILSCALE_UI_OK"); Qt.quit();
            }
        }
    }
    Timer { interval: 11000; running: true; onTriggered: Qt.quit() }
}
""")
            environment = dict(os.environ, DOTS_SHELL_SOURCE=str(base), DOTS_TAILSCALE_BINARY=str(binary),
                TAILSCALE_TEST_CALLS=str(base/'calls.jsonl'), TAILSCALE_TEST_STATE=str(base/'saved-state.json'), HYPRLAND_INSTANCE_SIGNATURE='isolated-tailscale-ui', XDG_CONFIG_HOME=str(base/'config'),
                XDG_STATE_HOME=str(base/'state'), XDG_CACHE_HOME=str(base/'cache'))
            launcher = environment.get('DOTS_TEST_LAUNCHER')
            command = [launcher] if launcher else [shutil.which('quickshell') or shutil.which('qs'), '-p', str(base)]
            result = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=16)
            logs = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, logs)
            self.assertIn('TAILSCALE_UI_OK', logs)
            calls = [json.loads(line) for line in (base/'calls.jsonl').read_text().splitlines()]
            for call in calls:
                self.assertTrue(call in (['down'], ['up']) or '--help' in call or call in (['status','--json'], ['switch','--list','--json'], ['debug','prefs']), call)
            self.assertEqual(calls.count(['down']), 1)
            self.assertEqual(calls.count(['up']), 1)
            self.assertEqual(json.loads((base/'saved-state.json').read_text()), {'running':True, 'hostname':'custom-device', 'operator':'saved-operator'})
            for error in ('Binding loop detected', 'Cannot open file', 'ReferenceError:', 'TypeError:', 'is not a type', 'Cannot assign', 'Unable to assign'):
                self.assertNotIn(error, logs)

if __name__ == '__main__': unittest.main()
