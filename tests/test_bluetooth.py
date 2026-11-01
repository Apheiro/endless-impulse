"""Pairing agent security/confirmation semantics and read-only native panel startup."""
import importlib.util
import os
import json
import select
import time
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock
from gi.repository import Gio, GLib

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'src/quickshell'
spec=importlib.util.spec_from_file_location('bluetooth_agent',SOURCE/'scripts/bluetooth/agent.py')
agent=importlib.util.module_from_spec(spec);spec.loader.exec_module(agent)
PATH='/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF'

class Invocation:
    def __init__(self):self.values=[];self.errors=[]
    def return_value(self,value):self.values.append(value.unpack())
    def return_dbus_error(self,name,message):self.errors.append((name,message))

class PairingAgentTests(unittest.TestCase):
    def setUp(self):
        self.events=[]
        self.a=object.__new__(agent.Agent)
        self.a.owner=':1.bluez';self.a.pending=None;self.a.timer=0;self.a.display_device=''
        self.a.emit=self.events.append
        self.a.call=Mock()
        self.addCleanup(self.a.cancel)
    def request(self,method,signature='(o)',values=(PATH,),sender=':1.bluez'):
        invocation=Invocation()
        self.a.method(None,sender,agent.AGENT_PATH,'org.bluez.Agent1',method,GLib.Variant(signature,values),invocation)
        return invocation
    def test_numeric_passkey_requires_explicit_response_and_preserves_leading_zero_input(self):
        invocation=self.request('RequestPasskey')
        self.assertFalse(invocation.values)
        prompt=self.a.pending['prompt']['id']
        with self.assertRaises(ValueError):self.a.command(dict(action='respond',prompt=prompt,accept=True,value='12a'))
        self.assertIsNotNone(self.a.pending)
        self.a.command(dict(id='reply',action='respond',prompt=prompt,accept=True,value='000042'))
        self.assertEqual(invocation.values,[(42,)])
        self.assertIsNone(self.a.pending)
    def test_confirmation_is_not_automatically_accepted_and_can_be_rejected(self):
        invocation=self.request('RequestConfirmation','(ou)',(PATH,7))
        self.assertEqual(self.a.pending['prompt']['code'],'000007')
        self.assertEqual(invocation.values,[])
        self.a.command(dict(action='respond',prompt=self.a.pending['prompt']['id'],accept=False))
        self.assertEqual(invocation.errors[0][0],'org.bluez.Error.Rejected')
    def test_sender_and_concurrent_requests_cannot_replace_an_active_prompt(self):
        outsider=self.request('RequestAuthorization',sender=':1.other')
        self.assertTrue(outsider.errors)
        self.assertIsNone(self.a.pending)
        first=self.request('RequestPinCode')
        second=self.request('RequestAuthorization')
        self.assertTrue(second.errors)
        self.assertEqual(self.a.pending['invocation'],first)
    def test_cancel_and_stale_response_never_confirm_pairing(self):
        invocation=self.request('RequestPinCode')
        prompt=self.a.pending['prompt']['id']
        self.request('Cancel','()',())
        with self.assertRaises(ValueError):self.a.command(dict(action='respond',prompt=prompt,accept=True,value='1234'))
        self.assertEqual(invocation.errors[0][0],'org.bluez.Error.Canceled')
        self.assertEqual(invocation.values,[])
    def test_display_passkey_returns_immediately_and_updates_entered_digits(self):
        invocation=self.request('DisplayPasskey','(ouq)',(PATH,17,2))
        self.assertEqual(invocation.values,[()])
        self.assertEqual(self.events[-1]['prompt']['code'],'000017')
        self.request('DisplayPasskey','(ouq)',(PATH,17,5))
        self.assertEqual(self.events[-1]['prompt']['entered'],5)
        self.assertIsNone(self.a.pending)
    def test_device_actions_validate_paths_and_forget_uses_own_adapter(self):
        with self.assertRaises(ValueError):self.a.command(dict(action='forget',device='/org/bluez/other'))
        self.a.call.assert_not_called()
        self.a.command(dict(action='forget',device=PATH))
        args=self.a.call.call_args.args
        self.assertEqual(args[:3],('/org/bluez/hci0','org.bluez.Adapter1','RemoveDevice'))
        self.assertEqual(args[3].unpack(),(PATH,))
    def test_hiding_visibility_keeps_agent_for_outgoing_pairing(self):
        invocation=self.request('RequestPinCode')
        self.a.command(dict(action='incoming',enable=False))
        self.a.call.assert_not_called()
        self.assertEqual(self.a.pending['invocation'],invocation)
        self.assertFalse(invocation.errors)

    def test_pin_bounds_and_service_authorization_need_user_consent(self):
        for value in ('','x'*17,'x\n',1234):
            with self.assertRaises(ValueError):agent.reply_value('RequestPinCode',value)
        invocation=self.request('AuthorizeService','(os)',(PATH,'service-uuid'))
        self.assertEqual(self.a.pending['prompt']['service'],'service-uuid')
        self.assertEqual(invocation.values,[])

@unittest.skipUnless(shutil.which('dbus-daemon'), 'Private D-Bus test needs dbus-daemon')
class BluezProtocolTests(unittest.TestCase):
    def test_pair_uses_same_agent_connection_and_propagates_connect_errors(self):
        with tempfile.TemporaryDirectory(prefix='ai-bluez-bus-') as temporary:
            base=Path(temporary)
            server=base/'bluez.py'
            server.write_text(FAKE_BLUEZ)
            busconfig=base/'bus.conf'
            busconfig.write_text('<busconfig><type>session</type><listen>unix:tmpdir='+str(base)+'</listen><auth>EXTERNAL</auth><policy context="default"><allow own="*"/><allow send_destination="*"/><allow receive_sender="*"/></policy></busconfig>')
            daemon=subprocess.Popen(['dbus-daemon','--config-file='+str(busconfig),'--nofork','--print-address=1'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            fake=None;helper=None
            try:
                self.assertTrue(select.select([daemon.stdout],[],[],4)[0], 'Private bus did not start')
                address=daemon.stdout.readline().strip()
                if not address:self.fail('Private D-Bus startup: '+daemon.stderr.read())
                env=dict(os.environ,DBUS_SYSTEM_BUS_ADDRESS=address)
                fake=subprocess.Popen(['python3',str(server)],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                self.assertTrue(select.select([fake.stdout],[],[],4)[0], 'Fake BlueZ did not start')
                startup=fake.stdout.readline().strip()
                if startup!='READY':self.fail('Fake BlueZ startup: '+fake.stderr.read())
                helper=subprocess.Popen(['python3',str(SOURCE/'scripts/bluetooth/agent.py')],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                buffered=b''
                def event(kind,identity=None):
                    nonlocal buffered
                    deadline=time.monotonic()+5
                    while time.monotonic()<deadline:
                        if b'\n' not in buffered:
                            if not select.select([helper.stdout],[],[],max(0,deadline-time.monotonic()))[0]:break
                            chunk=os.read(helper.stdout.fileno(),8192)
                            if not chunk:break
                            buffered+=chunk
                            continue
                        line,buffered=buffered.split(b'\n',1)
                        value=json.loads(line)
                        if value['event']==kind and (identity is None or value.get('id')==identity):return value
                    self.fail('No Bluetooth event: '+kind)
                def send(value):helper.stdin.write((json.dumps(value)+'\n').encode());helper.stdin.flush()
                self.assertTrue(event('ready')['ok'])
                send(dict(id='pair',action='pair',device=PATH))
                prompt=event('prompt')['prompt']
                self.assertEqual(prompt['kind'],'RequestConfirmation')
                self.assertEqual(prompt['code'],'000042')
                send(dict(id='answer',action='respond',prompt=prompt['id'],accept=True))
                self.assertTrue(event('result','answer')['ok'])
                self.assertTrue(event('result','pair')['ok'])
                send(dict(id='error',action='connect',device='/org/bluez/hci0/dev_00_00_00_00_00_00'))
                failure=event('result','error')
                self.assertFalse(failure['ok']);self.assertIn('Simulated connection error',failure['error'])
            finally:
                for process in (helper,fake,daemon):
                    if process:
                        process.terminate()
                        try:process.communicate(timeout=3)
                        except subprocess.TimeoutExpired:process.kill();process.communicate()


FAKE_BLUEZ = r'''import sys
from gi.repository import Gio,GLib
bus=Gio.bus_get_sync(Gio.BusType.SYSTEM,None)
xml="""<node>
<interface name="org.bluez.AgentManager1">
<method name="RegisterAgent"><arg type="o" direction="in"/><arg type="s" direction="in"/></method>
<method name="UnregisterAgent"><arg type="o" direction="in"/></method>
<method name="RequestDefaultAgent"><arg type="o" direction="in"/></method>
</interface>
<interface name="org.bluez.Device1"><method name="Pair"/><method name="Connect"/></interface>
</node>"""
interfaces=Gio.DBusNodeInfo.new_for_xml(xml).interfaces
state={}
def method(connection,sender,path,interface,method,args,invocation):
    if method=='RegisterAgent':state['owner']=sender;state['path']=args.unpack()[0];invocation.return_value(GLib.Variant('()',()))
    elif method in ('UnregisterAgent','RequestDefaultAgent'):invocation.return_value(GLib.Variant('()',()))
    elif method=='Pair':
        if sender!=state.get('owner'):
            invocation.return_dbus_error('org.bluez.Error.Rejected','Pair called by a different agent connection');return
        def confirmed(connection,result):
            try:
                connection.call_finish(result);state['confirmed']=True;invocation.return_value(GLib.Variant('()',()))
            except GLib.Error:invocation.return_dbus_error('org.bluez.Error.Rejected','Pair rejected')
        bus.call(sender,state['path'],'org.bluez.Agent1','RequestConfirmation',GLib.Variant('(ou)',(path,42)),None,Gio.DBusCallFlags.NONE,4000,None,confirmed)
    elif method=='Connect':
        if path.endswith('dev_00_00_00_00_00_00'):invocation.return_dbus_error('org.bluez.Error.Failed','Simulated connection error')
        elif not state.get('confirmed'):invocation.return_dbus_error('org.bluez.Error.Rejected','Not confirmed')
        else:invocation.return_value(GLib.Variant('()',()))
bus.register_object('/org/bluez',interfaces[0],method,None,None)
for path in ('/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF','/org/bluez/hci0/dev_00_00_00_00_00_00'):
    bus.register_object(path,interfaces[1],method,None,None)
Gio.bus_own_name_on_connection(bus,'org.bluez',Gio.BusNameOwnerFlags.NONE,lambda *_:print('READY',flush=True),None)
GLib.MainLoop().run()
'''

@unittest.skipUnless(os.environ.get('WAYLAND_DISPLAY'),'Bluetooth panel needs Wayland')
class BluetoothPanelTests(unittest.TestCase):
    def test_native_panel_and_pairing_prompt_load_without_changing_adapter(self):
        def adapter_properties():
            try:
                bus=Gio.bus_get_sync(Gio.BusType.SYSTEM,None)
                data=bus.call_sync('org.bluez','/','org.freedesktop.DBus.ObjectManager','GetManagedObjects',None,None,Gio.DBusCallFlags.NONE,2000,None).unpack()[0]
                return {path:{key:props['org.bluez.Adapter1'].get(key) for key in ('Powered','Discovering','Discoverable','Pairable')}
                        for path,props in data.items() if 'org.bluez.Adapter1' in props}
            except GLib.Error:return {}
        before=adapter_properties()
        with tempfile.TemporaryDirectory(prefix='ai-bluetooth-panel-') as temporary:
            base=Path(temporary)
            for name in ('modules','services','assets','scripts','defaults','translations','GlobalStates.qml'):
                (base/name).symlink_to(SOURCE/name,target_is_directory=(SOURCE/name).is_dir())
            (base/'shell.qml').write_text('''//@ pragma UseQApplication
import QtQuick
import Quickshell
import Quickshell.Wayland
import qs.services
import qs.modules.shared
import qs.modules.desktop.bluetooth
ShellRoot {
    id:root
    property int phase:0
    QtObject {
        id:ownedFlags
        property bool discovering:true
        property bool discoverable:true
        property bool pairable:true
        property int discoverableTimeout:180
    }
    PanelWindow {
        implicitWidth:850;implicitHeight:750;exclusiveZone:0;color:Appearance.colors.colLayer0
        WlrLayershell.namespace:"quickshell:bluetooth-test";WlrLayershell.keyboardFocus:WlrKeyboardFocus.None
        mask:Region{}
        BluetoothPanelContent{id:panel;anchors.fill:parent;anchors.margins:20}
    }
    function walk(item){if(item.objectName==="bluetooth-device-card")item.expanded=true;for(const child of item.children||[])walk(child);}
    Component.onCompleted:BluetoothManager.open()
    Timer {
        interval:500;running:true;repeat:true
        onTriggered:{
            if(!BluetoothManager.agentReady&&!BluetoothManager.failed)return;
            if(root.phase===0){root.walk(panel);BluetoothManager.prompt={id:"fixture",kind:"RequestConfirmation",device:"/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF",code:"000042"};root.phase++;}
            else if(root.phase===1){BluetoothManager.prompt={};root.phase++;}
            else if(root.phase===2){
                const image=Quickshell.env("DOTS_TEST_BLUETOOTH_IMAGE");if(image)panel.grabToImage(result=>result.saveToFile(image));root.phase++;
            }else{
                BluetoothManager.agentReady=false;
                BluetoothManager.scanOwner=ownedFlags;
                BluetoothManager.visibleOwner=ownedFlags;
                BluetoothManager.visiblePrevious={discoverable:false,pairable:false,timeout:60};
                BluetoothManager.close();
                if(ownedFlags.discovering || ownedFlags.discoverable || ownedFlags.pairable || ownedFlags.discoverableTimeout!==60){console.error("BLUETOOTH_FLAGS_NOT_RESTORED");Qt.quit();return;}
                console.log("BLUETOOTH_PANEL_OK");Qt.quit();
            }
        }
    }
    Timer{interval:10000;running:true;onTriggered:{console.error("BLUETOOTH_TIMEOUT",BluetoothManager.message);Qt.quit();}}
}''')
            env=dict(os.environ,DOTS_SHELL_SOURCE=str(base),XDG_CONFIG_HOME=str(base/'config'),XDG_STATE_HOME=str(base/'state'),XDG_CACHE_HOME=str(base/'cache'))
            launcher=env.get('DOTS_TEST_LAUNCHER')
            command=[launcher] if launcher else [shutil.which('quickshell'),'-p',str(base)]
            result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=15)
            logs=result.stdout+result.stderr
            self.assertEqual(result.returncode,0,logs)
            self.assertIn('BLUETOOTH_PANEL_OK',logs)
            for failure in ('TypeError:','ReferenceError:','Cannot assign','Binding loop','Unable to assign','Required property'):
                self.assertNotIn(failure,logs)
        self.assertEqual(adapter_properties(),before,'Opening the Bluetooth panel changed adapter flags')
