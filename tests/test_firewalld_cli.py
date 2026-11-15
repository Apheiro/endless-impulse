"""Bounded in-process CLI execution; scripts are disposable fixtures."""
import importlib.util
import io
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

BRIDGE = Path(__file__).resolve().parents[1] / 'src/quickshell/scripts/firewalld/control.py'
spec = importlib.util.spec_from_file_location('firewall_cli_bridge', BRIDGE)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class CliExecutionTests(unittest.TestCase):
    def test_upstream_preflight_bus_and_global_state_are_isolated(self):
        original_authorize = Mock(side_effect=AssertionError('Blanket authorization is forbidden'))
        original_nm_write = Mock(side_effect=AssertionError('NM writes are forbidden'))
        client = SimpleNamespace(FirewallClient=type('Client', (), {'authorizeAll': original_authorize}),
                                 exception_handler=None, not_authorized_loop=False)
        bus = Mock()
        bus_factory = Mock(return_value=bus)
        dbus = SimpleNamespace(SystemBus=bus_factory)
        network = SimpleNamespace(nm_set_zone_of_connection=original_nm_write)
        modules = {'firewall.client': client, 'dbus': dbus, 'firewall.core.fw_nm': network}
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / 'cli'
            script.write_text('''import sys
from importlib import import_module
client=import_module('firewall.client')
dbus=import_module('dbus')
assert client.exception_handler is None
assert not client.not_authorized_loop
client.FirewallClient().authorizeAll()
dbus.SystemBus()
client.exception_handler=lambda error: None
client.not_authorized_loop=True
sys.excepthook=lambda *args: None
print('isolated')
''')
            hook = sys.excepthook
            with patch.object(bridge.importlib, 'import_module', side_effect=modules.__getitem__):
                for _ in range(2):
                    self.assertEqual(bridge.Firewall(str(script)).run_cli([], 1).stdout, 'isolated\n')
                    self.assertIsNone(client.exception_handler)
                    self.assertFalse(client.not_authorized_loop)
                    self.assertIs(sys.excepthook, hook)
                    self.assertIs(client.FirewallClient.authorizeAll, original_authorize)
                    self.assertIs(network.nm_set_zone_of_connection, original_nm_write)
                with bridge.Firewall(str(script)).cli_environment():
                    with self.assertRaises(bridge.Failure) as error:
                        network.nm_set_zone_of_connection('home', 'fixture')
                    self.assertEqual(error.exception.state, 'conflict')
            self.assertEqual(bus_factory.call_count, 2)
            bus_factory.assert_called_with(private=True)
            self.assertEqual(bus.close.call_count, 2)
            original_authorize.assert_not_called()
            original_nm_write.assert_not_called()

    def test_output_exit_status_and_fresh_cli_globals(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / 'cli'
            script.write_text('''import sys
assert 'prior_run' not in globals()
prior_run=True
assert sys.stdin.read()==''
print('ñ '+sys.argv[1])
print('fixture error',file=sys.stderr)
raise SystemExit(7)
''')
            client = bridge.Firewall(str(script))
            original_argv, original_stdin = sys.argv, sys.stdin
            for _ in range(2):
                with patch.object(sys, 'stdin', io.StringIO('authorize\n')):
                    result = client.run_cli(['--fixture'], 1)
                    self.assertEqual(sys.stdin.read(), 'authorize\n')
                self.assertEqual(result.returncode, 7)
                self.assertEqual(result.stdout, 'ñ --fixture\n')
                self.assertEqual(result.stderr, 'fixture error\n')
                self.assertIs(sys.argv, original_argv)
                self.assertIs(sys.stdin, original_stdin)

    def test_timeout_restores_bridge_and_can_run_next_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / 'cli'
            script.write_text('import time\ntry: time.sleep(2)\nexcept Exception: raise SystemExit(1)\n')
            client = bridge.Firewall(str(script))
            handler = signal.getsignal(signal.SIGALRM)
            argv, stdin = sys.argv, sys.stdin
            with self.assertRaises(subprocess.TimeoutExpired):
                client.run_cli([], .03)
            self.assertIs(sys.argv, argv)
            self.assertIs(sys.stdin, stdin)
            self.assertEqual(signal.getsignal(signal.SIGALRM), handler)
            self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0, 0))
            script.write_text('print("recovered")\n')
            self.assertEqual(client.run_cli([], 1).stdout, 'recovered\n')

    def test_missing_host_bindings_are_an_intelligible_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / 'cli'
            script.write_text('raise ImportError("fixture missing host module")\n')
            with self.assertRaises(bridge.Failure) as error:
                bridge.Firewall(str(script)).run_cli([], 1)
            self.assertEqual(error.exception.state, 'communication-error')
            self.assertIn('host firewall-cmd Python dependencies', str(error.exception))


if __name__ == '__main__':
    unittest.main()
