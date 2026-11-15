"""Firewalld bridge contract. All subprocess calls are mocked; never contact a daemon."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'src/quickshell'
spec = importlib.util.spec_from_file_location('firewalld_control', SOURCE / 'scripts/firewalld/control.py')
fw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fw)

ZONES = '''home (active)
  target: default
  interfaces: test0
  sources:
  services: ssh
  ports: 8080/tcp
  forward: yes
  masquerade: no
  rich rules:
    rule family="ipv6" source address="2001:db8::/32" accept
    rule family="ipv4" source address="192.0.2.0/24" log prefix="test: unicode ñ" accept
trusted (active)
  target: ACCEPT
  interfaces: container-test
  services:
  ports:
'''
POLICIES = '''testPolicy (active)
  priority: -1
  target: CONTINUE
  ingress-zones: home
  egress-zones: HOST
  rich rules:
    rule service name="ssh" accept
'''


class FirewallTests(unittest.TestCase):
    def setUp(self):
        self.client = fw.Firewall('/fake/firewall-cmd')
        self.calls = []
        self.permission_patch = patch.object(self.client, 'permissions', return_value=True)
        self.permission_patch.start()
        self.owner_patch = patch.object(self.client, 'check_owner')
        self.owner_patch.start()
        def run(argv, **kwargs):
            self.calls.append(argv)
            self.assertNotIn('shell', kwargs)
            self.assertLessEqual(kwargs['timeout'], 60 if self.client.authorization_started else 5)
            self.assertEqual(kwargs['env']['LC_ALL'], 'C')
            option = argv[-1]
            output = {'--get-default-zone': 'home', '--list-all-zones': ZONES,
                      '--list-all-policies': POLICIES, '--get-services': 'ssh http https'}.get(option, 'success')
            return subprocess.CompletedProcess(argv, 0, output, '')
        self.runner = patch.object(fw.subprocess, 'run', side_effect=run).start()
        patch.object(self.client, 'run_cli', side_effect=lambda args, timeout: self.runner([self.client.binary, *args], timeout=timeout, env={'LC_ALL': 'C'})).start()
        self.addCleanup(patch.stopall)
        patch.object(self.client, 'connections', return_value=[]).start()
        self.state = self.client.snapshot()

    def request(self, action='add-service', value='http', scope='runtime', **kwargs):
        return dict(action=action, value=value, scope=scope, zone='home', revision=self.state['revision'], confirmed=True, **kwargs)

    def test_snapshot_real_round_trips_full_rules_and_modes(self):
        self.assertTrue(self.state['connected'])
        self.assertTrue(self.state['complete'])
        self.assertEqual(len(self.calls), 9)
        self.assertIn(['/fake/firewall-cmd', '--permanent', '--list-all-zones'], self.calls)
        self.assertEqual(self.state['defaultZone'], 'home')
        self.assertEqual(len(self.state['activeZones']), 2)
        self.assertEqual(self.state['scopes']['runtime']['policies'][0]['fields']['egress-zones'], 'HOST')
        rich = self.state['scopes']['runtime']['zones'][0]['fields']['rich rules']
        self.assertIn('2001:db8::/32', rich)
        self.assertIn('test: unicode ñ', rich)
        self.assertTrue(self.state['lastUpdated'])
        self.assertFalse(self.state['differences'])
        self.assertTrue(all('add-' not in ' '.join(call) for call in self.calls))

    def test_typed_arguments_and_scope(self):
        self.assertEqual(self.client.command(self.request(), self.state), ['--zone=home', '--add-service=http'])
        self.assertEqual(self.client.command(self.request('remove-port', '8080/tcp', 'permanent'), self.state),
                         ['--permanent', '--zone=home', '--remove-port=8080/tcp'])
        self.assertEqual(self.client.command(self.request('add-port', '8000-8010/udp'), self.state)[-1], '--add-port=8000-8010/udp')
        self.assertEqual(self.client.command(self.request('add-port', '00080-00080/tcp'), self.state)[-1], '--add-port=80/tcp')
        self.assertEqual(self.client.command(self.request('remove-forward', None), self.state)[-1], '--remove-forward')
        self.assertEqual(self.client.command(self.request('add-masquerade', None), self.state)[-1], '--add-masquerade')

    def test_validation_no_injection_unicode_or_option_injection(self):
        for value in ('$(touch /tmp/never)', '--reload', 'ssh;id', 'ssh\nhttp', 'ñ', 'ssh\0'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.client.command(self.request(value=value), self.state)
        for value in ('0/tcp', '65536/udp', '20-10/tcp', '80/sctp', '80/tcp --reload', '1-99999/tcp', '１/tcp', '80', None, 80):
            with self.subTest(port=value), self.assertRaises(ValueError):
                self.client.command(self.request('add-port', value), self.state)
        for zone in ('--reload', 'home;id', 'hôme', None):
            request = self.request(); request['zone'] = zone
            with self.assertRaises(ValueError): self.client.command(request, self.state)
        for action in ('reload', 'stop', 'set-default-zone', 'set-target', 'remove-zone', 'run'):
            with self.assertRaises(ValueError): self.client.command(self.request(action), self.state)
        for scope in ('both', '', None):
            with self.assertRaises(ValueError): self.client.command(self.request(scope=scope), self.state)

    def test_explicit_confirmation_revision_and_duplicates(self):
        for confirmed in (False, None, 'true', 1):
            request = self.request(); request['confirmed'] = confirmed
            with self.assertRaises(ValueError): self.client.command(request, self.state)
        request = self.request(); request['revision'] = 'old'
        with self.assertRaises(fw.Failure): self.client.command(request, self.state)
        for action, value in [('add-service', 'ssh'), ('remove-service', 'http'), ('add-port', '8080/tcp'), ('add-port', '08080-08080/tcp'), ('remove-masquerade', None)]:
            with self.assertRaises(fw.Failure): self.client.command(self.request(action, value), self.state)
        state = copy.deepcopy(self.state); state['complete'] = False
        with self.assertRaises(fw.Failure): self.client.command(self.request(), state)

    def test_error_classification_not_extrapolated_from_installation(self):
        for code, output, expected in [(252, 'FirewallD is not running', 'unavailable'),
                                       (1, 'NOT_AUTHORIZED', 'access-denied'),
                                       (1, 'DBUS_ERROR: Operation not permitted', 'access-denied'),
                                       (1, 'unrecognized response', 'communication-error')]:
            self.runner.side_effect = None
            self.runner.return_value = subprocess.CompletedProcess([], code, '', output)
            state = self.client.snapshot()
            self.assertEqual(state['state'], expected)
            self.assertFalse(state['connected'])
            self.assertFalse(state['complete'])
            self.assertFalse(state['scopes'])
        for error, expected in [(FileNotFoundError(), 'not-installed'),
                                (subprocess.TimeoutExpired('fake', 1), 'timeout'),
                                (OSError(), 'communication-error')]:
            self.runner.side_effect = error
            self.assertEqual(self.client.snapshot()['state'], expected)

    def test_partial_permission_failure_clears_data_but_preserves_reachability(self):
        self.runner.side_effect = [subprocess.CompletedProcess([], 0, 'home', ''), subprocess.CompletedProcess([], 1, '', 'NOT_AUTHORIZED')]
        state = self.client.snapshot()
        self.assertTrue(state['connected'])
        self.assertFalse(state['complete'])
        self.assertEqual(state['state'], 'access-denied')
        self.assertFalse(state['scopes'])
        self.assertIsNone(state['lastUpdated'])

    def test_external_change_conflict_prevents_mutation(self):
        changed = copy.deepcopy(self.state)
        changed['scopes']['runtime']['zones'][0]['fields']['ports'] = '9090/tcp'
        changed['revision'] = fw.revision(changed)
        with patch.object(self.client, 'snapshot', return_value=changed):
            self.calls.clear()
            result = self.client.handle(self.request())
        self.assertFalse(result['ok'])
        self.assertEqual(result['operationState'], 'conflict')
        self.assertEqual(self.calls, [])

    def test_mutation_and_uncertain_failure_always_refresh(self):
        with patch.object(self.client, 'snapshot', return_value=self.state) as snapshot:
            self.calls.clear()
            result = self.client.handle(self.request())
            self.assertTrue(result['ok'])
            self.assertEqual(snapshot.call_count, 2)
            self.assertEqual(self.calls, [['/fake/firewall-cmd', '--zone=home', '--add-service=http']])
        with patch.object(self.client, 'snapshot', return_value=self.state) as snapshot:
            self.runner.side_effect = subprocess.TimeoutExpired('fake', 1)
            result = self.client.handle(self.request())
            self.assertFalse(result['ok'])
            self.assertEqual(snapshot.call_count, 2)

    def test_postcondition_and_partial_result(self):
        applied = copy.deepcopy(self.state)
        applied['scopes']['runtime']['zones'][0]['fields']['services'] += ' http'
        with patch.object(self.client, 'snapshot', side_effect=[self.state, applied]):
            self.assertEqual(self.client.handle(self.request())['operationState'], 'applied')
        with patch.object(self.client, 'snapshot', return_value=self.state):
            self.assertEqual(self.client.handle(self.request())['operationState'], 'applied-unverified')
        unavailable = copy.deepcopy(self.state)
        unavailable.update(complete=False, connected=False, scopes={})
        with patch.object(self.client, 'snapshot', side_effect=[self.state, unavailable]):
            self.assertEqual(self.client.handle(self.request())['operationState'], 'applied-unverified')

    def test_malformed_output_fails_closed_and_no_auto_retry(self):
        self.runner.side_effect = [subprocess.CompletedProcess([], 0, 'home', ''),
                                   subprocess.CompletedProcess([], 0, '  orphan field', '')]
        result = self.client.snapshot()
        self.assertFalse(result['complete'])
        self.assertFalse(result['connected'])
        self.assertEqual(result['state'], 'communication-error')
        self.assertEqual(self.runner.call_count, 11)  # nine setup calls and exactly two failed-read calls

    def test_passive_permission_gate_never_launches_cli(self):
        self.calls.clear()
        self.client.permissions.return_value = False
        state = self.client.snapshot()
        self.assertEqual(state['state'], 'access-denied')
        self.assertFalse(state['complete'])
        self.assertEqual(self.calls, [])

    def test_explicit_challenge_requires_ack_before_cli_and_denial_does_not_retry(self):
        self.client.permissions.side_effect = [False] + [True] * 8
        with patch.object(self.client, 'check_permission', return_value=True), patch.object(fw.select, 'select', return_value=([fw.sys.stdin], [], [])), \
             patch.object(fw.sys.stdin, 'readline', return_value='authorize\n'), \
             patch('builtins.print') as event:
            result = self.client.handle({'action': 'snapshot', 'allowInteraction': True})
        self.assertTrue(result['snapshot']['complete'])
        self.assertTrue(self.client.authorization_started)
        self.assertEqual(event.call_count, 1)
        self.assertEqual(json.loads(event.call_args.args[0])['event'], 'authorization-required')
        self.calls.clear()
        self.client.authorization_started = False
        self.client.permissions.side_effect = None
        self.client.permissions.return_value = False
        with patch.object(fw.select, 'select', return_value=([], [], [])), patch('builtins.print'):
            result = self.client.handle({'action': 'snapshot', 'allowInteraction': True})
        self.assertEqual(result['snapshot']['state'], 'timeout')
        self.assertFalse(self.calls)
        self.client.permissions.return_value = True
        self.runner.side_effect = None
        self.runner.return_value = subprocess.CompletedProcess([], 1, '', 'NotAuthorizedException: Not Authorized(polkit)')
        result = self.client.handle({'action': 'snapshot', 'allowInteraction': True})
        self.assertEqual(result['snapshot']['state'], 'access-denied')

    def test_pkcheck_has_no_interaction_and_identifies_process(self):
        # Use the real permission checker with every external command mocked.
        self.permission_patch.stop()
        self.runner.side_effect = None
        self.runner.return_value = subprocess.CompletedProcess([], 1, '', '')
        with patch.object(fw.shutil, 'which', return_value='/fake/pkcheck'):
            self.assertFalse(self.client.permissions())
        argv = self.runner.call_args.args[0]
        self.assertNotIn('--allow-user-interaction', argv)
        self.assertNotIn('--enable-internal-agent', argv)
        self.assertRegex(argv[2], r'^\d+,\d+,\d+$')
        self.runner.return_value = subprocess.CompletedProcess([], 0, '', '')
        with patch.object(fw.shutil, 'which', return_value='/fake/pkcheck'):
            self.assertTrue(self.client.permissions())
        self.assertEqual(self.runner.call_args.args[0][-1], 'org.fedoraproject.FirewallD1.config.info')
        self.runner.return_value = subprocess.CompletedProcess([], 2, '', '')
        with patch.object(fw.shutil, 'which', return_value='/fake/pkcheck'):
            self.assertFalse(self.client.permissions())

    def test_pkcheck_exit_semantics_and_single_bounded_challenge(self):
        for code, diagnostic, interactive, expected in (
            (2, "Authorization requires authentication and -u wasn't passed.", False, False),
            (2, "No authentication agent found.", False, "agent-unavailable"),
            (2, "No authentication agent found.", True, "agent-unavailable"),
            (1, "Not authorized", True, "access-denied"),
            (3, "dismissed", True, "access-denied"),
            (127, "Error connecting to system bus", False, "communication-error"),
            (126, "Invalid option", False, "authorization-unavailable"),
            (0, "", True, True),
        ):
            with self.subTest(code=code, interactive=interactive):
                self.runner.side_effect = None
                self.runner.return_value = subprocess.CompletedProcess([], code, '', diagnostic)
                if isinstance(expected, str):
                    with self.assertRaises(fw.Failure) as failure:
                        self.client.check_permission('/fake/pkcheck', '1,2,3', 'config', interactive)
                    self.assertEqual(failure.exception.state, expected)
                else:
                    self.assertIs(self.client.check_permission('/fake/pkcheck', '1,2,3', 'config', interactive), expected)
                argv = self.runner.call_args.args[0]
                self.assertEqual('--allow-user-interaction' in argv, interactive)
                self.assertNotIn('--enable-internal-agent', argv)
        self.runner.side_effect = subprocess.TimeoutExpired('pkcheck', 60)
        with self.assertRaises(fw.Failure) as failure:
            self.client.check_permission('/fake/pkcheck', '1,2,3', 'config', True)
        self.assertEqual(failure.exception.state, 'timeout')

    def test_real_permission_gate_code2_then_one_challenge_or_failure(self):
        self.permission_patch.stop()
        cli_run = self.runner.side_effect
        for outcome, expected in ((0, 'connected'), (1, 'access-denied'),
                                  (3, 'access-denied'), (2, 'agent-unavailable')):
            with self.subTest(outcome=outcome):
                self.client.authorization_started = False
                authorized = False
                checks = []
                self.calls.clear()
                def run(argv, **kwargs):
                    nonlocal authorized
                    if argv[0] != '/fake/pkcheck':
                        return cli_run(argv, **kwargs)
                    checks.append(argv)
                    if '--allow-user-interaction' in argv:
                        authorized = outcome == 0
                        self.assertEqual(argv[4], 'org.fedoraproject.FirewallD1.config')
                        return subprocess.CompletedProcess(argv, outcome, '', 'No authentication agent' if outcome == 2 else '')
                    return subprocess.CompletedProcess(argv, 0 if authorized else 2, '', "Authorization requires authentication and -u wasn't passed.")
                self.runner.side_effect = run
                with patch.object(fw.shutil, 'which', return_value='/fake/pkcheck'), \
                     patch.object(fw.select, 'select', return_value=([fw.sys.stdin], [], [])), \
                     patch.object(fw.sys.stdin, 'readline', return_value='authorize\n'), \
                     patch('builtins.print') as event:
                    result = self.client.handle({'action': 'snapshot', 'allowInteraction': True})
                self.assertEqual(result['snapshot']['state'], expected)
                self.assertEqual(event.call_count, 1)
                self.assertEqual(sum('--allow-user-interaction' in argv for argv in checks), 1)
                self.assertEqual(len(self.calls), 9 if outcome == 0 else 0)

    def test_initial_authorization_failure_stops_before_cli_without_retry(self):
        for state in ('access-denied', 'agent-unavailable', 'timeout'):
            with self.subTest(state=state):
                self.client.authorization_started = False
                self.client.permissions.return_value = False
                self.calls.clear()
                with patch.object(self.client, 'authorize', side_effect=fw.Failure(state, state)) as authorize:
                    response = self.client.handle({'action': 'snapshot', 'allowInteraction': True})
                self.assertEqual(response['snapshot']['state'], state)
                authorize.assert_called_once()
                self.assertEqual(self.calls, [])
                with patch.object(self.client, 'authorize') as authorize:
                    self.client.handle({'action': 'snapshot', 'allowInteraction': False})
                authorize.assert_not_called()

    def test_owner_check_distinguishes_bus_failure_and_stopped_without_activation(self):
        self.owner_patch.stop()
        self.runner.side_effect = None
        for diagnostic, expected in [('Name has no owner', 'unavailable'), ('Call failed: no such name', 'unavailable'), ('Permission denied', 'communication-error')]:
            self.runner.return_value = subprocess.CompletedProcess([], 1, '', diagnostic)
            with self.assertRaises(fw.Failure) as failure:
                self.client.check_owner()
            self.assertEqual(failure.exception.state, expected)
            self.assertIn('--auto-start=no', self.runner.call_args.args[0])

    def test_snapshot_only_and_malformed_input(self):
        self.calls.clear()
        self.client.handle({'action': 'snapshot'})
        self.assertFalse(any('--add-' in str(call) for call in self.calls))
        with self.assertRaises(ValueError): self.client.handle([])


if __name__ == '__main__':
    unittest.main()
