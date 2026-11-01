#!/usr/bin/env python3
"""Install and activate Artificial Impulse's host services, without graphics drivers."""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / 'services/arch.json'


def run(arguments, check=True):
    return subprocess.run(arguments, check=check, capture_output=True, text=True, timeout=30)


def os_identity(path=Path('/etc/os-release')):
    values = {}
    for line in path.read_text().splitlines():
        key, separator, value = line.partition('=')
        if separator and not key.startswith('#'):
            parts = shlex.split(value)
            values[key] = ' '.join(parts)
    return values


def supported(identity):
    return identity.get('ID') == 'arch' or 'arch' in identity.get('ID_LIKE', '').split()


def unit_state(unit, user=False):
    result = run(['systemctl', *(['--user'] if user else []), 'show', unit,
                  '--property=LoadState,ActiveState,UnitFileState', '--no-pager'], check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or 'Could not contact the systemd user manager. Run from your logged-in desktop session.')
    return dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)


def installed(package):
    result = run(['pacman', '-Qq', package], check=False)
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.strip())
    return result.returncode == 0


def snapshot(groups):
    packages = sorted({package for group in groups for package in group['packages']})
    units = []
    for group in groups:
        for scope, key in [('system', 'systemUnits'), ('user', 'userUnits')]:
            for unit in group.get(key, []):
                units.append(dict(name=unit, scope=scope, group=group['name'], **unit_state(unit, scope == 'user')))
    return dict(missingPackages=[package for package in packages if not installed(package)], units=units)


def conflicts(status):
    problems = []
    if installed('pulseaudio'):
        problems.append('PulseAudio is installed. Select a migration to PipeWire before applying; this installer does not remove it automatically.')
    if installed('pipewire-media-session'):
        problems.append('pipewire-media-session is installed. Select a migration to WirePlumber before applying.')
    network = next(row for row in status['units'] if row['name'] == 'NetworkManager.service')
    if network.get('ActiveState') != 'active':
        for unit in ('systemd-networkd.service', 'connman.service', 'dhcpcd.service'):
            if unit_state(unit).get('ActiveState') == 'active':
                problems.append(f'{unit} already manages networking. Select a migration before activating NetworkManager.')
    for unit in ('tlp.service', 'auto-cpufreq.service', 'tuned.service'):
        if unit_state(unit).get('ActiveState') == 'active':
            problems.append(f'{unit} is active. Select a power manager before activating power-profiles-daemon.')
    for row in status['units']:
        if row.get('LoadState') == 'masked' or row.get('UnitFileState') == 'masked':
            problems.append(f'{row["name"]} is masked. Its administrator policy will not be overridden.')
    return problems


def activation_commands(units):
    commands = []
    for unit in units:
        if unit.get('LoadState') != 'loaded':
            raise RuntimeError(f'{unit["name"]} is unavailable after package installation.')
        prefix = ['sudo', 'systemctl'] if unit['scope'] == 'system' else ['systemctl', '--user']
        if unit.get('UnitFileState') not in ('enabled', 'enabled-runtime', 'static', 'indirect', 'alias'):
            commands.append([*prefix, 'enable', unit['name']])
        if unit.get('ActiveState') != 'active':
            commands.append([*prefix, 'start', unit['name']])
    return commands


def apply(status, groups, config_home):
    # Preflight happens before any privileged command or file mutation.
    problems = conflicts(status)
    if problems:
        raise RuntimeError('\n'.join(problems))
    if os.geteuid() == 0:
        raise RuntimeError('Run as your desktop user; sudo is used only for system packages and units.')
    uinput_needed = any(unit['name'] == 'ydotool.service' and unit.get('ActiveState') != 'active' for unit in status['units'])
    if uinput_needed and not Path('/dev/uinput').exists():
        run(['modprobe', '--dry-run', 'uinput'])
    module_file = Path('/etc/modules-load.d/artificial-impulse-uinput.conf')
    if uinput_needed and module_file.exists() and module_file.read_text() != (HERE / 'services/uinput.conf').read_text():
        raise RuntimeError(str(module_file) + ' already contains a different configuration; it will not be overwritten.')
    permission_rule = Path('/etc/udev/rules.d/70-artificial-impulse-uinput.rules')
    expected_rule = (HERE / 'services/70-artificial-impulse-uinput.rules').read_text()
    if uinput_needed and permission_rule.exists() and permission_rule.read_text() != expected_rule:
        raise RuntimeError(str(permission_rule) + ' already contains a different rule; it will not be overwritten.')
    if status['missingPackages']:
        subprocess.run(['sudo', 'pacman', '-S', '--needed', *status['missingPackages']], check=True)
    if uinput_needed:
        subprocess.run(['sudo', 'install', '-m', '0644', str(HERE / 'services/uinput.conf'), str(module_file)], check=True)
        subprocess.run(['sudo', 'modprobe', 'uinput'], check=True)
    if uinput_needed and not os.access('/dev/uinput', os.W_OK):
        subprocess.run(['sudo', 'install', '-m', '0644', str(HERE / 'services/70-artificial-impulse-uinput.rules'), str(permission_rule)], check=True)
        subprocess.run(['sudo', 'udevadm', 'control', '--reload-rules'], check=True)
        subprocess.run(['sudo', 'udevadm', 'trigger', '--action=change', '/sys/class/misc/uinput'], check=True)
    # UPower/Polkit/portals/GeoClue/secrets use D-Bus activation, not enable --now.
    refreshed = snapshot(groups)
    uinput = Path('/dev/uinput')
    deferred = []
    for unit in refreshed['units']:
        if unit['name'] == 'ydotool.service' and unit.get('ActiveState') != 'active' and not os.access(uinput, os.W_OK):
            deferred.append('Input automation: /dev/uinput is not writable. Grant the active desktop user access before starting ydotool.service.')
            continue
        for command in activation_commands([unit]):
            subprocess.run(command, check=True)
    # Install only a missing portal preference file; existing desktop choices stay intact.
    portal = config_home / 'xdg-desktop-portal/hyprland-portals.conf'
    if not portal.exists():
        portal.parent.mkdir(parents=True, exist_ok=True)
        try:
            with portal.open('x') as destination:
                destination.write((HERE / 'services/hyprland-portals.conf').read_text())
        except FileExistsError:
            pass
    if os.environ.get('WAYLAND_DISPLAY'):
        environment = ['WAYLAND_DISPLAY', 'XDG_CURRENT_DESKTOP']
        subprocess.run(['dbus-update-activation-environment', '--systemd', *[key for key in environment if os.environ.get(key)]], check=True)
    return deferred


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Install missing service packages and activate their system/user units')
    parser.add_argument('--json', action='store_true', help='Print the diagnostic as JSON; cannot be combined with --apply')
    args = parser.parse_args()
    if args.json and args.apply:
        parser.error('--json is a read-only diagnostic')
    if not supported(os_identity()):
        raise RuntimeError('Service installation currently supports Arch Linux and derivatives with systemd. The Nix application package remains independent of this installer.')
    if not Path('/run/systemd/system').is_dir() or not all(shutil.which(command) for command in ('systemctl', 'pacman')):
        raise RuntimeError('Arch with systemd and pacman is required. Run from the logged-in desktop session.')
    groups = json.loads(MANIFEST.read_text())['groups']
    status = snapshot(groups)
    status['conflicts'] = conflicts(status)
    status['groups'] = groups
    if args.json:
        print(json.dumps(status, indent=2))
        return
    print('Artificial Impulse — host services (graphics drivers excluded)')
    print('Missing packages: ' + (', '.join(status['missingPackages']) or 'none'))
    for unit in status['units']:
        print(f'  {unit["scope"]}: {unit["name"]} — {unit.get("ActiveState", "unknown")} / {unit.get("UnitFileState", "not installed")}')
    for group in groups:
        if group.get('activation'):
            print(f'  {group["name"]}: {group["activation"]}')
    for problem in status['conflicts']:
        print('Conflict: ' + problem)
    if not args.apply:
        print('Preview only. Use --apply to install and activate these services.')
        return
    pending = apply(status, groups, Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')))
    for message in pending:
        print('Pending: ' + message)
    if pending:
        raise RuntimeError('Core services are prepared; input automation still needs the permission reported above.')
    print('Services prepared. No graphics drivers or existing Hyprland configuration were changed.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
