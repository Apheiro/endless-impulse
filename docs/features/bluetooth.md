# Native Bluetooth panel

Right-clicking the Bluetooth symbol opens a compact panel at the upper-right of its monitor:
power, connected devices, connect/disconnect and explicit discovery. Left-click opens the notification sidebar, whose customizable Bluetooth button’s menu action
opens Settings → Bluetooth. Quick panels share surfaces, sizing and dismissal.
The advanced page contains adapter selection, device permissions and full details.

The panel provides adapter selection, power, filtered connected/saved/nearby
lists, battery, pairing/connection/disconnection and cancellation. Expand a device
to rename it, change trust/block/wake flags or forget it after confirmation.
Connected audio devices link to the audio panel's profile controls; PipeWire and
WirePlumber continue handling codecs and audio profiles.

Search is explicit and lasts at most 30 seconds. Only a search started here is
stopped when closing/changing adapter. **Make discoverable** requests the
agent role and makes the adapter discoverable/pairable for three minutes. Previous
flags/timeouts are restored when this mode ends or the panel closes. Opening the
panel never powers on an adapter, starts discovery or disconnects a device.

`services/BluetoothManager.qml` uses `Quickshell.Bluetooth` as the live model and
for power, discovery and device properties. `scripts/bluetooth/agent.py` runs on
the system D-Bus using Python GObject/GIO. Device operations with asynchronous
results (pair/connect/disconnect/forget) use that helper. Pair is issued from the
same D-Bus connection that registers the agent, so PIN and authorization callbacks
reach our panel instead of an unrelated default agent.

The KeyboardDisplay agent implements PIN/passkey entry/display, numeric comparison,
pairing authorization, service authorization, cancellation and release. Prompts
require explicit confirmation and expire after two minutes. Agent calls must come
from BlueZ's current unique bus owner. Closing/locking rejects pending prompts.
It never automatically trusts devices or accepts service authorization. The
helper unregisters on exit; incoming pairing requires this panel to be open.

A running host BlueZ service is required. Nix bundles Python/GIO, not a separate
Bluetooth daemon. Native Arch installs require `bluez` and `python-gobject`;
Fedora uses `bluez` and `python3-gobject`. BlueDevil is no longer required by the
shell. Existing installations/packages and custom app command overrides are not
removed automatically.

Compatibility command: `dots-shell ipc bluetooth open` (Nix) or the registered
`scripts/shell/control.py ipc bluetooth open` launcher. The IPC also supports
`toggle` and `close`. The legacy sidebar Details action opens this panel too.

Agent checks use fake invocations and a private D-Bus with a simulated BlueZ,
including complete confirm/pair/connect and error propagation. A read-only native
panel test checks adapter flags remain unchanged and renders an owned prompt.
Physical pairing, hardware switches, incoming service permissions and multiple
real adapters remain for the user's acceptance testing. No real device is paired,
forgotten or disconnected by these tests.
