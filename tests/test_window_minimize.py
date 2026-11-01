"""Exercise minimization without moving any real user window."""
import importlib.util
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('window_minimize', ROOT / 'src/quickshell/scripts/hyprland/minimize.py')
minimize = importlib.util.module_from_spec(spec)
spec.loader.exec_module(minimize)


class WindowMinimizeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        state_patch = patch.object(minimize, 'STATE', Path(temporary.name) / 'minimized.json')
        state_patch.start(); self.addCleanup(state_patch.stop)
        env_patch = patch.dict(os.environ, HYPRLAND_INSTANCE_SIGNATURE='minimize-fixture')
        env_patch.start(); self.addCleanup(env_patch.stop)
        self.clients = {
            '0xa': dict(address='0xa', pid=10, workspace=dict(id=3, name='3'), monitor=1, pinned=False, grouped=[]),
            '0xb': dict(address='0xb', pid=20, workspace=dict(id=4, name='4'), monitor=0, pinned=False, grouped=[]),
            '0xc': dict(address='0xc', pid=30, workspace=dict(id=-2, name='special:special'), monitor=0, pinned=False, grouped=[]),
        }
        self.active = '0xa'
        self.calls = []
        ipc_patch = patch.object(minimize, 'ipc', side_effect=self.ipc)
        ipc_patch.start(); self.addCleanup(ipc_patch.stop)

    def ipc(self, *arguments, json_result=False):
        self.calls.append(arguments)
        if arguments[0] == 'clients': return list(self.clients.values())
        if arguments[0] == 'activewindow': return dict(address=self.active)
        if arguments[0] == 'activeworkspace': return dict(id=7, name='7')
        if arguments[0] == 'eval':
            code = arguments[1]
            address = re.search(r'address:(0x[0-9a-f]+)', code)[1]
            if 'window.move' in code:
                target = re.search(r'workspace="([^"]+)"', code)[1]
                self.clients[address]['workspace'] = dict(id=-99 if target.startswith('special:') else 3 if target.startswith('name:') else int(target), name=target.removeprefix('name:'))
            else: self.active = address
            return 'ok'
        raise AssertionError(arguments)

    def test_toggle_hides_focused_window_and_restores_original_workspace(self):
        self.assertEqual(minimize.run('toggle', '0xa')['minimized'], ['0xa'])
        saved = json.loads(minimize.STATE.read_text())['windows']['0xa']
        self.assertEqual(saved['workspace'], dict(id=3, name='3'))
        self.assertEqual(self.clients['0xc']['workspace']['name'], 'special:special')
        self.assertEqual(minimize.run('toggle', '0xa')['minimized'], [])
        self.assertEqual(self.clients['0xa']['workspace'], dict(id=3, name='3'))
        self.assertEqual(self.active, '0xa')

    def test_click_on_inactive_window_focuses_instead_of_minimizing(self):
        self.active = '0xb'
        self.assertEqual(minimize.run('toggle', '0xa')['minimized'], [])
        self.assertEqual(self.active, '0xa')
        self.assertFalse(any('window.move' in str(call) for call in self.calls))

    def test_origin_survives_service_reload_and_named_workspaces(self):
        self.clients['0xa']['workspace'] = dict(id=3, name='work')
        minimize.run('minimize', '0xa')
        self.assertIn('0xa', minimize.load(self.clients))
        minimize.run('restore', '0xa')
        self.assertEqual(self.clients['0xa']['workspace']['name'], 'work')
        self.assertTrue(any('workspace="name:work"' in str(call) for call in self.calls))

    def test_original_scratchpad_window_returns_to_scratchpad(self):
        minimize.run('minimize', '0xc')
        minimize.run('restore', '0xc')
        self.assertEqual(self.clients['0xc']['workspace']['name'], 'special:special')

    def test_orphaned_minimized_window_can_be_recovered(self):
        self.clients['0xa']['workspace'] = dict(id=-99, name=minimize.WORKSPACE)
        minimize.run('restore', '0xa')
        self.assertEqual(self.clients['0xa']['workspace']['id'], 7)

    def test_closed_windows_and_reused_addresses_are_pruned(self):
        minimize.run('minimize', '0xa')
        self.clients['0xa']['pid'] = 99
        self.assertEqual(minimize.load(self.clients), {})
        del self.clients['0xa']
        minimize.run('status')
        self.assertEqual(json.loads(minimize.STATE.read_text())['windows'], {})

    def test_session_identity_prevents_restoring_stale_origins(self):
        minimize.run('minimize', '0xa')
        with patch.dict(os.environ, HYPRLAND_INSTANCE_SIGNATURE='different-session'):
            self.assertEqual(minimize.load(self.clients), {})
            minimize.run('restore', '0xa')
        self.assertEqual(self.clients['0xa']['workspace']['id'], 7)

    def test_restore_all_leaves_regular_scratchpad_alone(self):
        minimize.run('minimize', '0xa')
        minimize.run('minimize', '0xb')
        self.assertEqual(minimize.run('restore-all')['minimized'], [])
        self.assertEqual(self.clients['0xa']['workspace']['id'], 3)
        self.assertEqual(self.clients['0xb']['workspace']['id'], 4)
        self.assertEqual(self.clients['0xc']['workspace']['name'], 'special:special')

    def test_failed_dispatch_keeps_origin_for_recovery(self):
        original = self.ipc
        def fail(*arguments, **kwargs):
            if arguments[0] == 'eval': raise ValueError('IPC failure')
            return original(*arguments, **kwargs)
        with patch.object(minimize, 'ipc', side_effect=fail), self.assertRaises(ValueError):
            minimize.run('minimize', '0xa')
        self.assertEqual(json.loads(minimize.STATE.read_text())['windows']['0xa']['workspace']['id'], 3)

    def test_pinned_grouped_and_closed_windows_do_not_move(self):
        for attributes in [dict(pinned=True), dict(pinned=False, grouped=['0xb'])]:
            self.clients['0xa'].update(attributes)
            with self.assertRaises(ValueError): minimize.run('minimize', '0xa')
        with self.assertRaises(ValueError): minimize.run('restore', '0xdead')
        self.assertFalse(any('window.move' in str(call) for call in self.calls))
