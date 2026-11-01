#!/usr/bin/env python3
"""Read-only dependency map from the project manifest, with an offline bundle snapshot."""
import argparse
import hashlib
import json
from pathlib import Path

GROUPS = [
    ('desktop', 'Session & hardware', 'desktop_windows', 'The host session, hardware services and desktop authentication.',
     'hyprland wayland hypridle hyprlock hyprsunset mesa libdrm libxcb upower power-profiles-daemon dbus polkit geoclue polkit-kde-agent gnome-keyring xdg-user-dirs'),
    ('runtime', 'Interface & shared runtimes', 'code', 'Quickshell, Qt/QML, Python integration and formula rendering.',
     'quickshell qt6-5compat qt6-base qt6-declarative qt6-imageformats qt6-multimedia qt6-positioning qt6-quicktimeline qt6-sensors qt6-svg qt6-tools qt6-translations qt6-virtualkeyboard qt6-wayland qt6-avif-image-plugin kirigami syntax-highlighting glib2 gobject-introspection python-gobject nodejs npm uv'),
    ('audio', 'Audio & Bluetooth', 'volume_up', 'Audio services, application volumes, media controls and BlueZ devices.',
     'pipewire pipewire-audio pipewire-pulse wireplumber rtkit easyeffects libpipewire playerctl cava bluez bluez-utils'),
    ('network', 'Network & location', 'lan', 'NetworkManager connections, IP/DNS settings and hotspot sharing.',
     'networkmanager libnm dnsmasq wpa_supplicant'),
    ('capture', 'Recording, capture & clipboard', 'videocam', 'GPU recording, screenshots, region selection, image tools and clipboard history.',
     'gpu-screen-recorder hyprshot hyprpicker slurp swappy ffmpeg imagemagick wl-clipboard cliphist tesseract tesseract-data-eng'),
    ('appearance', 'Themes, fonts & application integration', 'palette', 'Wallpaper-derived colors, toolkit themes, fonts, icons and desktop portals.',
     'matugen breeze breeze-plus adw-gtk-theme-git bibata-cursor-theme-bin darkly-bin fontconfig gtk4 libadwaita gnome-desktop-4 libnotify libdbusmenu-gtk3 libportal-gtk4 xdg-desktop-portal xdg-desktop-portal-gtk xdg-desktop-portal-hyprland xdg-desktop-portal-kde otf-space-grotesk ttf-jetbrains-mono-nerd ttf-material-symbols-variable-git ttf-readex-pro ttf-rubik-vf ttf-twemoji'),
    ('tools', 'Desktop tools & integrations', 'construction', 'Utilities used by individual desktop features and configured application shortcuts.',
     'brightnessctl ddcutil dolphin systemsettings plasma-workspace kdialog kitty fish fuzzel libqalculate translate-shell songrec wlogout wtype ydotool'),
    ('build', 'Build & command-line support', 'terminal', 'Build tools and command-line helpers included by the installer.',
     'bc clang cmake cpptrace coreutils curl eza go-yq jemalloc jq libsoup3 procps-ng ripgrep rsync starship wget'),
]
HOST = set('wpa_supplicant dbus polkit rtkit power-profiles-daemon easyeffects pipewire-audio bluez-utils hyprland wayland bluez networkmanager pipewire pipewire-pulse wireplumber upower geoclue gnome-keyring polkit-kde-agent xdg-desktop-portal xdg-desktop-portal-gtk xdg-desktop-portal-hyprland xdg-desktop-portal-kde'.split())
FEATURE = set('dnsmasq hyprlock dolphin systemsettings plasma-workspace kdialog kitty fish fuzzel translate-shell songrec wlogout cava'.split())
BUILD = set('clang cmake cpptrace'.split())
DETAILS = {
    'hyprland': 'Wayland compositor: windows, workspaces, monitors and effects.',
    'wayland': 'Display protocol libraries for the desktop session.',
    'quickshell': 'The native desktop interface, panels and Settings.',
    'qt6-base': 'Qt runtime shared by the interface and controls.',
    'qt6-declarative': 'QML and Qt Quick: interface layout, interaction and animation.',
    'python-gobject': 'Python GObject/GIO integration for NetworkManager and the BlueZ pairing agent.',
    'gobject-introspection': 'Native library type information used by Python integrations.',
    'nodejs': 'JavaScript runtime for MathJax formula rendering.',
    'npm': 'Installs the formula renderer dependencies from the npm lockfile.',
    'uv': 'Manages the Python environment for native installations; Nix has its own pinned runtime.',
    'bluez': 'Host Bluetooth service. The shell provides its own device and pairing interface.',
    'pipewire': 'Host media server. The shell provides volume, device and routing controls.',
    'pipewire-pulse': 'PulseAudio-compatible interface used by pactl and applications.',
    'wireplumber': 'Host media policy, device profiles and audio routing.',
    'networkmanager': 'Host network service for Wi-Fi, Ethernet, profiles, VPN and IP/DNS settings.',
    'libnm': 'Native NetworkManager client library and introspection used by the shell.',
    'dnsmasq': 'Feature-specific support for connection sharing and Wi-Fi hotspots.',
    'gpu-screen-recorder': 'GPU video recording. The runtime prefers the host binary and can use its Nix fallback.',
    'matugen': 'Generates the shared color palette from the wallpaper.',
    'polkit-kde-agent': 'Host permission prompts for privileged desktop operations; still required by those operations.',
    'gnome-keyring': 'Host secret storage for compatible applications and integrations.',
    'hyprlock': 'Fallback lock screen when the native Quickshell lock cannot run.',
    'systemsettings': 'External KDE configuration tools retained for configured integrations.',
    'plasma-workspace': 'KDE desktop integration utilities retained by the installer.',
    'dolphin': 'Default file-manager integration; independent of the shell network and Bluetooth panels.',
}
MANIFESTS = ['installer/dependencies/arch.json', 'installer/distros/fedora/feddeps.toml', 'packaging/nix/runtime.nix', 'packaging/nix/package.nix', 'flake.lock', 'runtime/math/package-lock.json']


def build(root):
    root = Path(root)
    path = root / MANIFESTS[0]
    manifest = json.loads(path.read_text())
    origin = {name: 'Repository' for name in manifest['repository']}
    origin.update({name: 'AUR' for name in manifest['aur']})
    remaining = set(origin)
    groups = []
    for identity, title, icon, description, names in GROUPS:
        packages = sorted(set(names.split()) & remaining)
        remaining.difference_update(packages)
        nodes = []
        for name in packages:
            scope = 'Host service / session' if name in HOST else 'Build tool' if name in BUILD else 'Feature-specific tool' if name in FEATURE else 'Runtime / client tool'
            purpose = DETAILS.get(name, description)
            nodes.append(dict(id='package:'+name, title=name, package=name, description=purpose, scope=scope, origin=origin[name], declared=True, children=[], uses=[purpose], tags=[scope, origin[name]]))
        groups.append(dict(id='group:'+identity, title=title, icon=icon, description=description, count=len(nodes), children=nodes, tags=[], uses=[description]))
    if remaining:
        groups.append(dict(id='group:other', title='Other declared dependencies', icon='inventory_2', description='Additional entries from the installation manifest.', count=len(remaining), children=[dict(id='package:'+name, title=name, package=name, description='Declared by the installer; consult the manifest for its integration.', scope='Runtime / client tool', origin=origin[name], declared=True, children=[], uses=[], tags=[]) for name in sorted(remaining)], tags=[], uses=[]))
    shared=next(group for group in groups if group['id']=='group:runtime')
    shared['children'] += [
        dict(id='module:python',title='Python 3',description='Shared interpreter for audio, network, Bluetooth and system helpers. Supplied by the host Python environment or pinned by Nix.',scope='Shared runtime',origin='Python / Nix',declared=False,children=[],uses=['python interpreter'],tags=['runtime']),
        dict(id='module:mathjax',title='MathJax',description='Renders formulas locally through Node.js. Exact npm dependencies are recorded in the formula lockfile.',scope='Formula rendering',origin='npm',declared=False,children=[],uses=['mathjax formulas latex'],tags=['runtime']),
    ]
    shared['count']=len(shared['children'])
    network=next(group for group in groups if group['id']=='group:network')
    network['children'].append(dict(id='optional:vpn',title='VPN provider plugins',description='Provider-based VPNs such as OpenVPN need a matching host plugin and compatible importer. WireGuard is native to NetworkManager.',scope='Optional host integration',optional=True,origin='',declared=False,children=[],uses=['vpn OpenVPN OpenConnect plugins import'],tags=['optional']))
    network['count']=len(network['children'])
    return dict(schema=1, reference='Arch Linux', total=len(origin), repository=len(manifest['repository']), aur=len(manifest['aur']), groups=groups, manifests=MANIFESTS, fingerprint=hashlib.sha256(path.read_bytes()).hexdigest())


def discover(script):
    return next((p for p in Path(script).resolve().parents if (p / MANIFESTS[0]).is_file()), None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path)
    parser.add_argument('--snapshot', action='store_true')
    args = parser.parse_args()
    shell = Path(__file__).resolve().parents[2]
    root = args.root or discover(__file__)
    snapshot = shell / 'defaults/dependencies.json'
    data = build(root) if root else json.loads(snapshot.read_text())
    if not args.snapshot:
        data['sources'] = [dict(name=path, path=str(root/path)) for path in data['manifests'] if root and (root/path).is_file()]
        if snapshot.is_file():data['sources'].append(dict(name='Bundled map snapshot', path=str(snapshot)))
        data['liveManifest'] = root is not None
    print(json.dumps(data, ensure_ascii=False))


if __name__ == '__main__':main()
