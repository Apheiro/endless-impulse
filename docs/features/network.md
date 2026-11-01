# Native network panel

The shell talks to the host NetworkManager through libnm/GIO in a separate,
event-driven Python process. No periodic nmcli subprocesses or KDE network panel
are used. Opening the panel reads state; scans and changes are explicit actions.
The bar, classic quick settings and alternative Wi-Fi controls use this service.
Right-clicking the network symbol opens a compact panel at the upper-right of the selected screen, showing
the current connection, Wi-Fi networks and credential prompts. The notification sidebar’s customizable network button provides a menu action
for Settings → Network with full interface and profile management. Re-enabling Wi-Fi
requests a scan once each managed adapter is ready, with bounded retries during
wake-up and no continuous background scanning.

## Management

- Interfaces: carrier, speed, addresses, gateways, DNS, routes, MAC, connection
  state and disconnect; Wi-Fi radio and global networking controls. Configure
  opens the active profile, or the selected profile for a disconnected interface.
  The explicit interface remains the target for Apply & test.
- Wi-Fi: grouped access points, signal, frequency, security, adapter selection,
  saved networks, hidden networks and hotspot on capable adapters.
- Authentication: WPA/WPA2, WPA3, OWE, open/legacy WEP and enterprise
  PEAP/TTLS/TLS, certificates, server domain and identity.
- Saved profiles: create, activate, rename, clone, delete inactive profiles,
  autoconnect, metering, MTU and cloned MAC. IPv4/IPv6 support DHCP, static
  addresses, DNS/search domains, default-route policy, metrics and static routes.
- The editor separates Connection, IPv4, IPv6, VPN and Advanced tabs. Each IP
  family has labeled Addressing, DNS and Routing groups; switching tabs retains
  drafts without saving them. Saved profile management stays separate.
- OpenVPN has guided server, authentication, certificate, password and optional
  security fields. WireGuard has private keys, listen port, allowed networks and
  peer configuration. Other VPN plugins expose named properties and masked
  credentials; their specialized browser/authentication flows are not embedded.
  OpenVPN field names follow the [upstream plugin definitions](https://github.com/NetworkManager/NetworkManager-openvpn/blob/main/shared/nm-service-defines.h).
- Import NetworkManager keyfiles, WireGuard wg-quick and typed settings JSON.
  VPN formats use installed NetworkManager importer plugins. Export omits all
  secrets and creates private files (0600).
- Guided creation includes Ethernet, Wi-Fi, hotspot, WireGuard, VPN, VLAN,
  bridge, bond and PPPoE. New/imported profiles open their editor automatically.
  Virtual profiles need their additional properties filled in before connecting.
- The advanced typed editor preserves settings outside the guided form and
  supports the installed libnm schema. Its searchable reference includes property
  names, D-Bus types and descriptions. This exposes advanced settings, but is not
  a specialized graphical editor for every VPN plugin or cellular protocol.

## Changes and credentials

Saving updates the profile without reconnecting. Apply & test and switching an
active interface create a NetworkManager checkpoint with a 45-second timeout.
Keep confirms; Revert, closing the panel or the daemon timeout restores the
previous connection. The timeout belongs to NetworkManager and survives a shell
crash. A previously disconnected interface has no active link to restore.
Checkpoint creation errors cancel the change. Profiles changed elsewhere require
reloading before saving, using NetworkManager's version-id update check.

The secret agent uses the same system-bus connection as activation. It only accepts
requests from NetworkManager for activations initiated by this panel, while open
and unlocked. It does not take over unrelated apps' password prompts. Passwords
travel through the private helper input and D-Bus, never command arguments,
environment variables, state events or exports. Credentials are cleared after
submission/cancellation. Explicitly saved new credentials are owned by
NetworkManager; existing keyring agents retain their role. The shell does not
implement a persistent keyring or plugin-specific VPN challenge/browser UI.
Retrieval failure aborts an edit rather than risking loss of saved credentials.

## Host integration

Run NetworkManager and the existing session PolicyKit agent. Native installs need
libnm introspection and Python GObject (Arch: networkmanager, libnm,
python-gobject; Fedora: NetworkManager, NetworkManager-libnm, python3-gobject).
Nix pins the client and typelibs; the host still owns devices, permissions and
NetworkManager service. Hotspot sharing needs the host's dnsmasq support.

VPN protocols need their matching daemon plugin on the host. Importers also need
the matching libnm editor plugin visible to the Python runtime; a host plugin
with an incompatible Nix ABI is not loaded automatically. Missing support gives
an error. Existing supported VPN profiles can be activated independently of an
importer. These plugin-specific editors, modem/SIM workflows and persistent
keyring storage remain integration work before claiming complete KDE feature
parity.

## Verification

`./dev check` includes disconnected libnm profile/route round trips, secret-agent
ownership and cancellation, mocked permission failures, checkpoint ordering,
rollback/confirmation and read-only QML startup. Automated network tests never
switch the user's connection or save real profiles. The user is the primary
tester for actual Wi-Fi, hotspot, VPN, certificate authentication and rollback on
their equipment.
