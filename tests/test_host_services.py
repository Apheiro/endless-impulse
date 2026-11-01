"""Service installation planning and conflict guards without modifying the host."""
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('host_services', ROOT / 'packaging/nix/services.py')
services = importlib.util.module_from_spec(spec)
spec.loader.exec_module(services)
GROUPS = json.loads(services.MANIFEST.read_text())['groups']


class HostServiceTests(unittest.TestCase):
    def test_manifest_includes_services_and_excludes_graphics_drivers(self):
        packages = {package for group in GROUPS for package in group['packages']}
        self.assertTrue({'networkmanager', 'bluez', 'pipewire', 'pipewire-pulse', 'wireplumber',
                         'polkit', 'dbus', 'upower', 'xdg-desktop-portal-hyprland', 'easyeffects'} <= packages)
        self.assertFalse(any(name.startswith(('nvidia', 'linux', 'xf86-')) or name in ('mesa', 'hyprland') for name in packages))
        arch = json.loads((ROOT / 'installer/dependencies/arch.json').read_text())
        self.assertTrue(packages <= set(arch['repository']))
        self.assertEqual((ROOT / 'packaging/nix/services/hyprland-portals.conf').read_text(),
                         (ROOT / 'config/xdg/config/xdg-desktop-portal/hyprland-portals.conf').read_text())

    def test_preview_queries_only_and_reports_missing_packages(self):
        calls = []
        def query(command, check=True):
            calls.append(command)
            if command[:2] == ['pacman', '-Qq']:
                return SimpleNamespace(returncode=int(command[-1] == 'bluez'), stdout='', stderr='')
            self.assertIn('show', command)
            return SimpleNamespace(returncode=0, stdout='LoadState=loaded\nActiveState=active\nUnitFileState=enabled\n', stderr='')
        with patch.object(services, 'run', side_effect=query):
            status = services.snapshot(GROUPS)
        self.assertEqual(status['missingPackages'], ['bluez'])
        self.assertTrue(all(command[0] in ('pacman', 'systemctl') for command in calls))
        self.assertTrue(all(not set(command) & {'start', 'restart', 'stop', 'enable', 'sudo', '-S'} for command in calls))
        self.assertNotIn('xdg-desktop-portal.service', [unit['name'] for unit in status['units']])

    def test_activation_does_not_restart_active_services_or_enable_static_units(self):
        units = [dict(name='NetworkManager.service', scope='system', LoadState='loaded', ActiveState='active', UnitFileState='enabled'),
                 dict(name='bluetooth.service', scope='system', LoadState='loaded', ActiveState='inactive', UnitFileState='disabled'),
                 dict(name='pipewire.socket', scope='user', LoadState='loaded', ActiveState='active', UnitFileState='enabled'),
                 dict(name='example.service', scope='user', LoadState='loaded', ActiveState='inactive', UnitFileState='static')]
        commands = services.activation_commands(units)
        self.assertEqual(commands, [['sudo', 'systemctl', 'enable', 'bluetooth.service'],
                                    ['sudo', 'systemctl', 'start', 'bluetooth.service'],
                                    ['systemctl', '--user', 'start', 'example.service']])
        with self.assertRaisesRegex(RuntimeError, 'unavailable'):
            services.activation_commands([dict(name='missing.service', scope='user', LoadState='not-found')])

    def test_conflicts_block_all_writes(self):
        status = dict(missingPackages=['bluez'], units=[dict(name='NetworkManager.service', ActiveState='inactive')])
        with patch.object(services, 'installed', side_effect=lambda name: name == 'pulseaudio'), \
             patch.object(services, 'unit_state', return_value={'ActiveState': 'inactive'}), \
             patch.object(services.subprocess, 'run') as mutation:
            with tempfile.TemporaryDirectory() as temporary:
                with self.assertRaisesRegex(RuntimeError, 'PulseAudio'):
                    services.apply(status, GROUPS, Path(temporary))
                self.assertEqual(list(Path(temporary).iterdir()), [])
            mutation.assert_not_called()

    def test_existing_network_manager_and_masked_units_are_preserved(self):
        status = {'units': [dict(name='NetworkManager.service', ActiveState='inactive'),
                            dict(name='bluetooth.service', LoadState='masked')]}
        with patch.object(services, 'installed', return_value=False), \
             patch.object(services, 'unit_state', side_effect=lambda unit, user=False: {'ActiveState': 'active' if unit == 'systemd-networkd.service' else 'inactive'}):
            problems = services.conflicts(status)
        self.assertTrue(any('systemd-networkd' in problem for problem in problems))
        self.assertTrue(any('masked' in problem for problem in problems))

    def test_apply_preserves_preferences_and_active_services(self):
        units = [dict(name='NetworkManager.service', scope='system', LoadState='loaded', ActiveState='active', UnitFileState='enabled')]
        status = dict(missingPackages=[], units=units)
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary)
            portal = config / 'xdg-desktop-portal/hyprland-portals.conf'
            portal.parent.mkdir()
            portal.write_text('personal configuration\n')
            with patch.object(services, 'conflicts', return_value=[]), \
                 patch.object(services.os, 'geteuid', return_value=1000), \
                 patch.object(services, 'snapshot', return_value=status), \
                 patch.dict(services.os.environ, {'WAYLAND_DISPLAY': ''}), \
                 patch.object(services.subprocess, 'run') as mutation:
                self.assertEqual(services.apply(status, GROUPS, config), [])
                mutation.assert_not_called()
            self.assertEqual(portal.read_text(), 'personal configuration\n')

    def test_install_only_missing_packages_and_register_native_units(self):
        before = dict(missingPackages=['bluez'], units=[dict(name='NetworkManager.service', scope='system', ActiveState='active')])
        after = dict(missingPackages=[], units=[dict(name='NetworkManager.service', scope='system', LoadState='loaded', ActiveState='active', UnitFileState='enabled'),
                    dict(name='bluetooth.service', scope='system', LoadState='loaded', ActiveState='inactive', UnitFileState='disabled')])
        with tempfile.TemporaryDirectory() as temporary, \
             patch.object(services, 'conflicts', return_value=[]), \
             patch.object(services.os, 'geteuid', return_value=1000), \
             patch.object(services, 'snapshot', return_value=after), \
             patch.dict(services.os.environ, {'WAYLAND_DISPLAY': 'wayland-test', 'XDG_CURRENT_DESKTOP': 'Hyprland'}), \
             patch.object(services.subprocess, 'run') as mutation:
            services.apply(before, GROUPS, Path(temporary))
            commands = [call.args[0] for call in mutation.call_args_list]
            self.assertEqual(commands[0], ['sudo', 'pacman', '-S', '--needed', 'bluez'])
            self.assertIn(['sudo', 'systemctl', 'enable', 'bluetooth.service'], commands)
            self.assertIn(['sudo', 'systemctl', 'start', 'bluetooth.service'], commands)
            self.assertFalse(any('restart' in command or 'NetworkManager.service' in command for command in commands))
            self.assertTrue((Path(temporary) / 'xdg-desktop-portal/hyprland-portals.conf').is_file())
            self.assertIn(['dbus-update-activation-environment', '--systemd', 'WAYLAND_DISPLAY', 'XDG_CURRENT_DESKTOP'], commands)

    def test_supported_hosts(self):
        self.assertTrue(services.supported({'ID': 'arch'}))
        self.assertTrue(services.supported({'ID': 'derivative', 'ID_LIKE': 'arch'}))
        self.assertFalse(services.supported({'ID': 'ubuntu', 'ID_LIKE': 'debian'}))


if __name__ == '__main__':
    unittest.main()
