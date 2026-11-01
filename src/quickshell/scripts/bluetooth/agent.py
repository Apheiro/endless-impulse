#!/usr/bin/env python3
"""Scoped BlueZ pairing agent. JSON lines transport; device state stays in Quickshell."""
import json
import os
import re
import signal
import sys
import uuid
from gi.repository import Gio, GLib, GLibUnix

AGENT_PATH = '/org/artificialimpulse/BluetoothAgent'
XML = '''<node><interface name="org.bluez.Agent1">
<method name="Release"/><method name="Cancel"/>
<method name="RequestPinCode"><arg type="o" direction="in"/><arg type="s" direction="out"/></method>
<method name="DisplayPinCode"><arg type="o" direction="in"/><arg type="s" direction="in"/></method>
<method name="RequestPasskey"><arg type="o" direction="in"/><arg type="u" direction="out"/></method>
<method name="DisplayPasskey"><arg type="o" direction="in"/><arg type="u" direction="in"/><arg type="q" direction="in"/></method>
<method name="RequestConfirmation"><arg type="o" direction="in"/><arg type="u" direction="in"/></method>
<method name="RequestAuthorization"><arg type="o" direction="in"/></method>
<method name="AuthorizeService"><arg type="o" direction="in"/><arg type="s" direction="in"/></method>
</interface></node>'''
DEVICE = re.compile(r'^/org/bluez/hci[0-9]+/dev_(?:[0-9A-Fa-f]{2}_){5}[0-9A-Fa-f]{2}$')


def reply_value(kind, value):
    if kind == 'RequestPinCode':
        if not isinstance(value, str) or not 1 <= len(value) <= 16 or any(ord(c)<32 for c in value):
            raise ValueError('Enter a PIN of 1–16 characters.')
        return GLib.Variant('(s)', (value,))
    if kind == 'RequestPasskey':
        if not isinstance(value, str) or not re.fullmatch(r'[0-9]{1,6}', value):
            raise ValueError('Enter a numeric passkey of up to six digits.')
        return GLib.Variant('(u)', (int(value),))
    return GLib.Variant('()', ())


class Agent:
    def __init__(self, bus, emit):
        self.bus, self.emit = bus, emit
        self.owner = ''
        self.pending = None
        self.timer = 0
        self.display_device = ''
        self.loop = GLib.MainLoop()
        self.buffer = b''
        self.registration = bus.register_object(AGENT_PATH, Gio.DBusNodeInfo.new_for_xml(XML).interfaces[0], self.method, None, None)
        Gio.bus_watch_name_on_connection(bus, 'org.bluez', Gio.BusNameWatcherFlags.NONE, self.appeared, self.vanished)

    def call(self, path, interface, method, parameters, callback, timeout=15000):
        def done(connection, result):
            try:
                value = connection.call_finish(result)
                callback(value, None)
            except GLib.Error as error:
                callback(None, error.message)
        self.bus.call('org.bluez', path, interface, method, parameters, None, Gio.DBusCallFlags.NONE, timeout, None, done)

    def appeared(self, connection, name, owner):
        self.owner = owner
        self.call('/org/bluez', 'org.bluez.AgentManager1', 'RegisterAgent', GLib.Variant('(os)', (AGENT_PATH, 'KeyboardDisplay')),
                  lambda value, error: self.emit(dict(event='ready', ok=not error, error=error or '')))

    def vanished(self, *_):
        self.owner = ''
        self.cancel()
        self.emit(dict(event='ready', ok=False, error='BlueZ is unavailable. Start the Bluetooth service and retry.'))

    def cancel(self):
        if self.timer:
            GLib.source_remove(self.timer); self.timer = 0
        if self.pending:
            self.pending['invocation'].return_dbus_error('org.bluez.Error.Canceled', 'Pairing request canceled.')
            self.pending = None
        self.display_device = ''
        self.emit(dict(event='prompt', prompt={}))

    def expired(self):
        self.timer = 0
        self.cancel()
        self.emit(dict(event='notice', error='The pairing request expired.'))
        return False

    def method(self, connection, sender, path, interface, method, parameters, invocation):
        if sender != self.owner:
            invocation.return_dbus_error('org.bluez.Error.Rejected', 'Only BlueZ may call this agent.'); return
        args = parameters.unpack()
        if method in ('Release', 'Cancel'):
            self.cancel(); invocation.return_value(GLib.Variant('()', ()))
            if method == 'Release': self.emit(dict(event='ready', ok=False, error='Bluetooth agent was released. Reopen the panel to register it again.'))
            return
        device = args[0]
        if not DEVICE.fullmatch(device):
            invocation.return_dbus_error('org.bluez.Error.Rejected', 'Invalid device.'); return
        display = method in ('DisplayPinCode', 'DisplayPasskey')
        if self.pending or (self.display_device and self.display_device != device):
            invocation.return_dbus_error('org.bluez.Error.Rejected', 'Another pairing request is awaiting confirmation.'); return
        prompt = dict(id=uuid.uuid4().hex, kind=method, device=device, code='', entered=0, service='')
        if method == 'DisplayPinCode': prompt['code'] = args[1]
        if method in ('DisplayPasskey', 'RequestConfirmation'): prompt['code'] = f'{args[1]:06d}'
        if method == 'DisplayPasskey': prompt['entered'] = args[2]
        if method == 'AuthorizeService': prompt['service'] = args[1]
        if self.timer: GLib.source_remove(self.timer)
        self.timer = GLib.timeout_add_seconds(120, self.expired)
        if display:
            self.display_device = device
            invocation.return_value(GLib.Variant('()', ()))
        else:
            self.pending = dict(prompt=prompt, invocation=invocation)
        self.emit(dict(event='prompt', prompt=prompt))

    def command(self, payload):
        identity = payload.get('id', '')
        def result(value=None, error=None):
            self.emit(dict(event='result', id=identity, ok=not error, error=error or ''))
        operation = payload.get('action')
        if operation == 'respond':
            pending = self.pending
            if not pending or pending['prompt']['id'] != payload.get('prompt'):
                raise ValueError('This pairing request is no longer active.')
            if payload.get('accept') is not True:
                pending['invocation'].return_dbus_error('org.bluez.Error.Rejected', 'Rejected by the user.')
            else:
                pending['invocation'].return_value(reply_value(pending['prompt']['kind'], payload.get('value', '')))
            self.pending = None
            if self.timer: GLib.source_remove(self.timer); self.timer = 0
            self.emit(dict(event='prompt', prompt={}))
            result(); return
        if operation == 'incoming':
            if payload.get('enable') is True:
                self.call('/org/bluez', 'org.bluez.AgentManager1', 'RequestDefaultAgent', GLib.Variant('(o)', (AGENT_PATH,)), result)
            else:
                # Keep our registered agent for outgoing requests until the panel closes.
                # BlueZ has no separate ReleaseDefaultAgent; unregistering here would
                # cancel an unrelated outgoing pairing in the same panel.
                result()
            return
        device = payload.get('device', '')
        if not isinstance(device, str) or not DEVICE.fullmatch(device): raise ValueError('Select a valid Bluetooth device.')
        if operation == 'forget':
            self.call(device.rsplit('/', 1)[0], 'org.bluez.Adapter1', 'RemoveDevice', GLib.Variant('(o)', (device,)), result)
        elif operation in ('connect', 'disconnect', 'cancel'):
            method = {'connect':'Connect', 'disconnect':'Disconnect', 'cancel':'CancelPairing'}[operation]
            self.call(device, 'org.bluez.Device1', method, None, result)
        elif operation == 'pair':
            def paired(value, error):
                if self.display_device == device or (self.pending and self.pending['prompt']['device'] == device):
                    self.cancel()
                if error: result(error=error)
                else: self.call(device, 'org.bluez.Device1', 'Connect', None, result)
            self.call(device, 'org.bluez.Device1', 'Pair', None, paired, timeout=120000)
        else:
            raise ValueError('Unknown Bluetooth action.')

    def stdin(self, fd, condition):
        try: chunk = os.read(fd, 8192)
        except BlockingIOError: return True
        if not chunk: self.shutdown(); return False
        self.buffer += chunk
        if len(self.buffer)>65536: self.shutdown(); return False
        while b'\n' in self.buffer:
            line, self.buffer = self.buffer.split(b'\n', 1)
            payload = {}
            try:
                payload = json.loads(line)
                if not isinstance(payload, dict): raise ValueError('Expected a Bluetooth command object.')
                self.command(payload)
            except (ValueError, TypeError, KeyError, GLib.Error) as error:
                self.emit(dict(event='result', id=payload.get('id', '') if isinstance(payload,dict) else '', ok=False, error=str(error)))
        return True

    def shutdown(self, *_):
        self.cancel()
        if self.owner:
            try:
                self.bus.call_sync('org.bluez','/org/bluez','org.bluez.AgentManager1','UnregisterAgent',GLib.Variant('(o)',(AGENT_PATH,)),None,Gio.DBusCallFlags.NONE,1000,None)
            except GLib.Error: pass
        self.loop.quit()
        return False


def main():
    def emit(value):
        try: print(json.dumps(value), flush=True)
        except BrokenPipeError: pass
    try:
        agent = Agent(Gio.bus_get_sync(Gio.BusType.SYSTEM, None), emit)
        os.set_blocking(0, False)
        GLib.io_add_watch(0, GLib.IO_IN | GLib.IO_HUP, agent.stdin)
        GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, agent.shutdown)
        agent.loop.run()
    except GLib.Error as error:
        emit(dict(event='ready', ok=False, error=error.message)); return 1
    return 0


if __name__ == '__main__': sys.exit(main())
