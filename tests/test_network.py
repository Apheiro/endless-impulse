"""libnm profile validation and secret handling with disposable, disconnected settings."""
import importlib.util
import base64
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import Mock,patch
import gi
gi.require_version('NM','1.0')
from gi.repository import NM,GLib

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'src/quickshell'
spec=importlib.util.spec_from_file_location('network_control',SOURCE/'scripts/network/control.py')
net=importlib.util.module_from_spec(spec);spec.loader.exec_module(net)

class NetworkProfilesTests(unittest.TestCase):
    def test_create_wifi_and_enterprise_without_exposing_secrets(self):
        for security in ('wpa-psk','sae','enterprise','open','owe','wep'):
            profile=net.create_profile(dict(name='Test',ssid='Test',security=security,password='password123',identity='user'))
            self.assertTrue(profile.verify())
            document=json.dumps(net.typed_document(profile))
            self.assertNotIn('password123',document)
            restored=net.from_document(json.loads(document))
            self.assertEqual(profile.get_uuid(),restored.get_uuid())
    def test_ip_routes_dns_and_unknown_fields_survive_roundtrip(self):
        profile=net.create_profile(dict(name='Wired',kind='ethernet'))
        profile=net.edit_profile(profile,dict(ipv4=dict(method='manual',addresses=['10.1.1.20/24'],gateway='10.1.1.1',dns=['1.1.1.1'],routes=[dict(destination='10.2.0.0/16',gateway='10.1.1.2',metric=5)])))
        original=net.typed_document(profile)
        restored=net.from_document(json.loads(json.dumps(original)))
        self.assertEqual(original,net.typed_document(restored))
        changed=net.edit_profile(restored,dict(ipv4=dict(dns=['9.9.9.9'])))
        self.assertEqual(changed.get_setting_ip4_config().get_num_addresses(),1)
        self.assertEqual(changed.get_setting_ip4_config().get_num_routes(),1)
        self.assertEqual(profile.get_setting_ip4_config().get_dns(0),'1.1.1.1')
    def test_bad_network_values_do_not_change_original_profile(self):
        profile=net.create_profile(dict(name='Wired',kind='ethernet'))
        before=net.typed_document(profile)
        for settings in [dict(ipv4=dict(method='manual',addresses=[])),dict(ipv4=dict(method='manual',addresses=['::1/128'])),dict(ipv4=dict(dns=['not-an-ip'])),dict(mtu=-1)]:
            with self.assertRaises((ValueError,GLib.Error)):net.edit_profile(profile,settings)
        self.assertEqual(before,net.typed_document(profile))
    def test_schema_includes_advanced_settings_and_secret_flags(self):
        schema={item['name']:item['properties'] for item in net.setting_schema()}
        for name in ('ipv4','ipv6','wireguard','vpn','vlan','bridge','bond','802-1x'):self.assertIn(name,schema)
        self.assertTrue(next(prop for prop in schema['802-11-wireless-security'] if prop['name']=='psk')['secret'])
    def test_import_export_keyfile_roundtrip_without_secrets(self):
        profile=net.create_profile(dict(name='Test',ssid='Test',security='wpa-psk',password='password123'))
        clean=NM.SimpleConnection.new_from_dbus(profile.to_dbus(NM.ConnectionSerializationFlags.NO_SECRETS))
        keyfile=NM.keyfile_write(clean,NM.KeyfileHandlerFlags.NONE,None,None)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'profile.nmconnection';path.write_text(keyfile.to_data()[0])
            self.assertNotIn('password123',path.read_text())
            restored=net.import_profile(path);self.assertEqual(restored.get_uuid(),profile.get_uuid())


class NetworkVpnTests(unittest.TestCase):
    @staticmethod
    def key(value):return base64.b64encode(bytes([value])*32).decode()
    def test_openvpn_visual_fields_preserve_other_properties_and_hide_secrets(self):
        profile=net.create_profile({'kind':'vpn','name':'VPN'})
        profile.get_setting_vpn().add_data_item('remote-random','yes')
        edited=net.edit_profile(profile,{'vpn':{'data':{'remote':'vpn.example.com','port':'443','proto-tcp':'yes','connection-type':'password','username':'test-user'},'secrets':{'password':'test-password'}}})
        self.assertEqual(edited.get_setting_vpn().get_data_item('remote-random'),'yes')
        self.assertIsNone(profile.get_setting_vpn().get_data_item('remote'))
        self.assertEqual(edited.get_setting_vpn().get_secret('password'),'test-password')
        self.assertNotIn('test-password',json.dumps(net.profile_settings(edited)))
        self.assertNotIn('test-password',json.dumps(net.typed_document(edited)))
        self.assertEqual(net.profile_settings(edited)['vpn']['data']['remote'],'vpn.example.com')
        for data in ({'port':'65536'},{'connection-type':'bad'},{'remote':''}):
            with self.assertRaises(ValueError):net.edit_profile(edited,{'vpn':{'data':data}})
    def test_wireguard_peer_changes_and_secret_preservation(self):
        profile=net.create_profile({'kind':'wireguard','name':'WG','interfaceName':'wg-test'})
        row=dict(publicKey=self.key(2),endpoint='vpn.example.com:51820',allowedIps=['10.20.0.0/16'],keepalive=25,presharedKey=self.key(3))
        profile=net.edit_profile(profile,{'wireguard':{'privateKey':self.key(1),'listenPort':51820,'peers':[row]}})
        row=dict(row,endpoint='vpn.example.com:443');del row['presharedKey']
        edited=net.edit_profile(profile,{'wireguard':{'peers':[row]}})
        wg=edited.get_setting_by_name('wireguard')
        self.assertEqual(wg.get_peer(0).get_preshared_key(),self.key(3))
        self.assertEqual(wg.props.private_key,self.key(1))
        self.assertEqual(profile.get_setting_by_name('wireguard').get_peer(0).get_endpoint(),'vpn.example.com:51820')
        safe=json.dumps(net.profile_settings(edited))+json.dumps(net.typed_document(edited))
        self.assertNotIn(self.key(1),safe);self.assertNotIn(self.key(3),safe)
        self.assertEqual(net.profile_settings(edited)['wireguard']['peers'][0]['endpoint'],'vpn.example.com:443')
        for value in ({'privateKey':'bad-key'},{'peers':[dict(row,endpoint='bad-endpoint')]},{'listenPort':65536},{'peers':[row,row]}):
            with self.assertRaises((ValueError,GLib.Error)):net.edit_profile(profile,{'wireguard':value})
    def test_removed_wireguard_peer_does_not_block_preserving_private_key(self):
        profile=net.create_profile({'kind':'wireguard','name':'WG','interfaceName':'wg-test'})
        profile=net.edit_profile(profile,{'wireguard':{'privateKey':self.key(1),'peers':[dict(publicKey=self.key(2),allowedIps=['10.0.0.0/8'],presharedKey=self.key(3))]}})
        clone=net.edit_profile(NM.SimpleConnection.new_from_dbus(profile.to_dbus(NM.ConnectionSerializationFlags.NO_SECRETS)),{'wireguard':{'peers':[]}})
        controller=object.__new__(net.Controller);controller.emit=Mock();controller.changed=Mock()
        remote=Mock();remote.get_secrets_finish.return_value=profile.to_dbus(NM.ConnectionSerializationFlags.ONLY_SECRETS)
        completed=Mock();controller.preserve_secrets(remote,clone,{'id':'save'},completed)
        remote.get_secrets_async.call_args.args[-1](remote,object())
        completed.assert_called_once()
        self.assertEqual(clone.get_setting_by_name('wireguard').get_peers_len(),0)
        self.assertEqual(clone.get_setting_by_name('wireguard').props.private_key,self.key(1))

    def test_disabling_family_clears_only_that_family(self):
        profile=net.create_profile({'kind':'ethernet','name':'Local'})
        profile=net.edit_profile(profile,{'ipv4':{'method':'manual','addresses':['10.0.0.2/24'],'gateway':'10.0.0.1','dns':['1.1.1.1']},'ipv6':{'method':'manual','addresses':['2001:db8::2/64']}})
        edited=net.edit_profile(profile,{'ipv4':{'method':'disabled'}})
        self.assertEqual(edited.get_setting_ip4_config().get_num_addresses(),0)
        self.assertEqual(edited.get_setting_ip6_config().get_num_addresses(),1)
        self.assertEqual(profile.get_setting_ip4_config().get_num_addresses(),1)

class NetworkRecoveryTests(unittest.TestCase):
    """Checkpoint operations use a fake daemon; never alter the tester's link."""
    def setUp(self):
        self.events=[];self.c=object.__new__(net.Controller)
        self.c.client=Mock();self.c.emit=self.events.append;self.c.changed=Mock()
        self.c.checkpoint=None;self.c.checkpoint_pending=False
        self.c.radio_generation=0;self.c.enable_scan_timer=0;self.c.enable_scan_deadline=0;self.c.enable_scan_pending=set();self.c.enable_scan_running=set();self.c.scan_watches={}
    def test_changes_wait_for_checkpoint_and_rollback_destroys_it(self):
        device=Mock();action=Mock();payload={'id':'test'}
        self.c.protect(device,payload,action)
        action.assert_not_called();self.assertTrue(self.c.checkpoint_pending)
        self.assertEqual(self.c.client.checkpoint_create.call_args.args[1],45)
        self.c.client.checkpoint_create_finish.return_value.get_path.return_value='/checkpoint/test'
        self.c.client.checkpoint_create.call_args.args[-1](self.c.client,object())
        action.assert_called_once();self.assertEqual(self.c.checkpoint['path'],'/checkpoint/test')
        with self.assertRaises(ValueError):self.c.protect(device,payload,action)
        self.c.rollback(payload)
        self.c.client.checkpoint_destroy.assert_not_called()
        self.c.client.checkpoint_rollback.call_args.args[-1](self.c.client,object())
        self.c.client.checkpoint_destroy.assert_called_once()
        self.c.client.checkpoint_destroy.call_args.args[-1](self.c.client,object())
        self.assertTrue(self.events[-1]['ok'])
    def test_checkpoint_failure_never_runs_disruptive_action(self):
        action=Mock();self.c.protect(Mock(),{'id':'test'},action)
        self.c.client.checkpoint_create_finish.side_effect=GLib.Error('Denied')
        self.c.client.checkpoint_create.call_args.args[-1](self.c.client,object())
        action.assert_not_called();self.assertFalse(self.events[-1]['ok'])
    def test_keep_and_panel_close_use_destroy_and_rollback_respectively(self):
        self.c.checkpoint={'path':'/checkpoint/test'};self.c.agent=Mock()
        self.c.command({'action':'keep','id':'keep'})
        self.c.client.checkpoint_destroy.assert_called_once()
        self.c.command({'action':'panel','open':False,'id':'close'})
        self.c.agent.cancel.assert_called_once()
        self.c.client.checkpoint_rollback.assert_called_once()
    def test_failed_secret_preservation_aborts_the_profile_write(self):
        remote=Mock();remote.get_secrets_finish.side_effect=GLib.Error('Denied')
        clone=net.create_profile(dict(name='Test',ssid='Test'))
        action=Mock();self.c.preserve_secrets(remote,clone,{'id':'save'},action)
        remote.get_secrets_async.call_args.args[-1](remote,object())
        action.assert_not_called();self.assertFalse(self.events[-1]['ok'])
        self.assertIn('preserve',self.events[-1]['error'])
    def test_new_password_wins_while_old_credentials_are_preserved(self):
        original=net.create_profile(dict(name='Test',ssid='Test',password='old-password'))
        clean=NM.SimpleConnection.new_from_dbus(original.to_dbus(NM.ConnectionSerializationFlags.NO_SECRETS))
        clone=net.edit_profile(clean,{'password':'new-password','mac':'random'})
        remote=Mock();remote.get_secrets_finish.return_value=original.to_dbus(NM.ConnectionSerializationFlags.ONLY_SECRETS)
        completed=Mock();self.c.preserve_secrets(remote,clone,{'id':'save'},completed)
        remote.get_secrets_async.call_args.args[-1](remote,object())
        completed.assert_called_once()
        self.assertEqual(clone.get_setting_wireless_security().props.psk,'new-password')
        self.assertEqual(clone.get_setting_wireless().props.cloned_mac_address,'random')
        self.assertEqual(original.get_setting_wireless_security().props.psk,'old-password')

    def test_radio_and_network_permissions_report_async_errors(self):
        bus=self.c.client.get_dbus_connection.return_value
        bus.call_finish.side_effect=GLib.Error('Not authorized')
        for action in ('wifi','networking'):
            self.c.command({'action':action,'enabled':False,'id':action})
            bus.call.call_args.args[-1](bus,object())
            self.assertFalse(self.events[-1]['ok'])
            self.assertIn('Not authorized',self.events[-1]['error'])

class NetworkAutoScanTests(unittest.TestCase):
    def setUp(self):
        self.events=[];self.c=object.__new__(net.Controller)
        self.c.client=Mock();self.c.emit=self.events.append;self.c.changed=Mock()
        self.c.radio_generation=0;self.c.enable_scan_timer=0;self.c.enable_scan_deadline=0;self.c.enable_scan_pending=set();self.c.enable_scan_running=set();self.c.scan_watches={}
        self.device=Mock(spec=NM.DeviceWifi)
        self.device.get_path.return_value='/device/wifi'
        self.device.get_managed.return_value=True
        self.device.get_last_scan.return_value=-1
        self.device.get_state.return_value=NM.DeviceState.UNAVAILABLE
        self.c.client.get_devices.return_value=[self.device]
        self.c.client.wireless_get_enabled.return_value=False
        timer=patch.object(GLib,'timeout_add_seconds',return_value=123);timer.start();self.addCleanup(timer.stop)
        remove=patch.object(GLib,'source_remove');remove.start();self.addCleanup(remove.stop)
        disconnect=patch.object(net.GObject,'signal_handler_disconnect');disconnect.start();self.addCleanup(disconnect.stop)
    def test_enable_waits_for_radio_and_adapter_before_searching(self):
        self.c.command({'action':'wifi','enabled':True,'id':'enable'})
        self.device.request_scan_async.assert_not_called()
        bus=self.c.client.get_dbus_connection.return_value
        bus.call.call_args.args[-1](bus,object())
        self.device.request_scan_async.assert_not_called()
        self.c.client.wireless_get_enabled.return_value=True
        self.c.scan_enabled_wifi();self.device.request_scan_async.assert_not_called()
        self.device.get_state.return_value=NM.DeviceState.DISCONNECTED
        self.c.scan_enabled_wifi();self.device.request_scan_async.assert_called_once()
        self.c.scan_enabled_wifi();self.device.request_scan_async.assert_called_once()
        self.device.request_scan_async.call_args.args[-1](self.device,object())
        self.assertFalse(self.c.scan_enabled_wifi())
        self.assertFalse(self.c.enable_scan_pending)
    def test_transient_scan_error_retries_but_expiry_stops(self):
        self.c.client.wireless_get_enabled.return_value=True
        self.device.get_state.return_value=NM.DeviceState.ACTIVATED
        self.c.queue_enabled_scans()
        self.device.request_scan_finish.side_effect=GLib.Error('Still waking')
        self.device.request_scan_async.call_args.args[-1](self.device,object())
        self.c.scan_enabled_wifi();self.assertEqual(self.device.request_scan_async.call_count,2)
        self.c.enable_scan_deadline=0
        self.assertFalse(self.c.scan_enabled_wifi())
        self.assertEqual(self.events[-1]['event'],'scan-error')
        self.assertFalse(self.c.enable_scan_pending)
    def test_indicator_stays_until_nm_reports_scan_completion(self):
        self.device.get_state.return_value=NM.DeviceState.DISCONNECTED
        self.c.client.wireless_get_enabled.return_value=True
        self.c.queue_enabled_scans()
        self.device.request_scan_async.call_args.args[-1](self.device,object())
        self.assertFalse(self.c.enable_scan_pending)
        self.assertIn('/device/wifi',self.c.scan_watches)
        self.device.get_last_scan.return_value=12345
        self.device.connect.call_args.args[1]()
        self.assertFalse(self.c.scan_watches)
    def test_manual_scan_indicator_ends_on_error_or_timeout(self):
        self.c.device=Mock(return_value=self.device)
        self.c.command({'action':'scan','device':'/device/wifi','id':'scan'})
        self.assertTrue(self.c.scan_watches)
        self.device.request_scan_finish.side_effect=GLib.Error('Unavailable')
        self.device.request_scan_async.call_args.args[-1](self.device,object())
        self.assertFalse(self.c.scan_watches)
        self.c.begin_scan_watch(self.device)
        with patch.object(GLib,'timeout_add_seconds',return_value=123) as timer:
            self.c.begin_scan_watch(self.device)
            timer.call_args.args[1]()
        self.assertFalse(self.c.scan_watches)

    def test_turning_wifi_back_off_cancels_pending_search(self):
        self.c.queue_enabled_scans()
        self.c.command({'action':'wifi','enabled':False,'id':'disable'})
        self.assertFalse(self.c.enable_scan_pending)
        self.assertFalse(self.c.scan_enabled_wifi())
        self.device.request_scan_async.assert_not_called()

class Invocation:
    def __init__(self):self.values=[];self.errors=[]
    def return_value(self,value):self.values.append(value)
    def return_dbus_error(self,name,message):self.errors.append((name,message))

class NetworkSecretTests(unittest.TestCase):
    def setUp(self):
        self.events=[];self.controller=Mock();self.controller.emit=self.events.append;self.controller.client.get_dbus_name_owner.return_value=':1.nm';self.controller.owned={'owned'};self.controller.panel_open=True
        self.agent=object.__new__(net.SecretAgent);self.agent.controller=self.controller;self.agent.pending=None
    def request(self,identity='owned',sender=':1.nm',flags=1):
        invocation=Invocation()
        data={'connection':{'uuid':GLib.Variant('s',identity),'id':GLib.Variant('s','Test')},'802-11-wireless-security':{'key-mgmt':GLib.Variant('s','wpa-psk')}}
        params=GLib.Variant('(a{sa{sv}}osasu)',(data,'/connection/test','802-11-wireless-security',[],flags))
        self.agent.method(None,sender,net.AGENT_PATH,net.SECRETS_IFACE,'GetSecrets',params,invocation)
        return invocation
    def test_agent_does_not_intercept_other_apps_or_noninteractive_requests(self):
        for args in [dict(identity='other'),dict(sender=':1.other'),dict(flags=0)]:
            invocation=self.request(**args);self.assertTrue(invocation.errors);self.assertIsNone(self.agent.pending)
    def test_credentials_stay_in_dbus_reply_and_cancel_clears_prompt(self):
        invocation=self.request();token=self.agent.pending['id']
        self.assertFalse(invocation.values)
        self.agent.respond(dict(prompt=token,accept=True,values={'psk':'password123'}))
        self.assertEqual(invocation.values[0].unpack()[0]['802-11-wireless-security']['psk'],'password123')
        self.assertNotIn('password123',json.dumps(self.events))
        invocation=self.request();self.agent.cancel();self.assertTrue(invocation.errors)

@unittest.skipUnless(os.environ.get('WAYLAND_DISPLAY'),'Network panel needs Wayland')
class NetworkPanelTests(unittest.TestCase):
    def test_interface_config_and_profile_sections_keep_drafts_without_writes(self):
        wired=net.create_profile({'name':'Ethernet fixture','kind':'ethernet'})
        vpn=net.edit_profile(net.create_profile({'name':'OpenVPN fixture','kind':'vpn'}),{'vpn':{'data':{'remote':'vpn.example.com','connection-type':'password','username':'fixture'}}})
        wg=net.edit_profile(net.create_profile({'name':'WireGuard fixture','kind':'wireguard','interfaceName':'wg-fixture'}),{'wireguard':{'peers':[{'publicKey':NetworkVpnTests.key(2),'endpoint':'vpn.example.com:51820','allowedIps':['10.0.0.0/8'],'keepalive':25}]}})
        generic=net.create_profile({'name':'Plugin fixture','kind':'vpn','service':'org.freedesktop.NetworkManager.custom'})
        generic.get_setting_vpn().add_data_item('gateway','vpn.example.com')
        fixtures=[dict(uuid=profile.get_uuid(),document=net.typed_document(profile),settings=net.profile_settings(profile),version=1) for profile in (wired,vpn,wg,generic)]
        with tempfile.TemporaryDirectory(prefix='ai-network-editor-') as temporary:
            base=Path(temporary)
            for name in ('modules','services','assets','scripts','defaults','translations','GlobalStates.qml'):(base/name).symlink_to(SOURCE/name)
            text='''//@ pragma UseQApplication
import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Wayland
import qs.services
import qs.modules.shared
import qs.modules.desktop.network
ShellRoot {
 id:root
 property var fixtures:__FIXTURES__
 property int index:0
 property int phase:0
 property var fixtureDevice:({id:"fixture-device",interface:"fixture-ethernet",kind:"ethernet",state:"activated",active:"profile-b",profiles:["profile-a","profile-b"],carrier:true,speed:1000,hw:"",reason:"none",ip4:{},ip6:{}})
 function find(item,name){if(item.objectName===name)return item;for(const child of item.children||[]){const found=find(child,name);if(found)return found;}return null;}
 function fail(message){console.error("EDITOR_FAILED",message);Qt.quit();}
 PanelWindow {
  implicitWidth:1000;implicitHeight:950;exclusiveZone:0;color:Appearance.colors.colLayer0
  WlrLayershell.namespace:"quickshell:network-editor-test";WlrLayershell.keyboardFocus:WlrKeyboardFocus.None
  mask:Region{}
  ColumnLayout {
   id:body;anchors.fill:parent;anchors.margins:20
   NetworkDeviceCard{id:card;device:root.fixtureDevice;visible:root.phase===0}
   Loader{id:editor;Layout.fillWidth:true;sourceComponent:editorComponent}
  }
 }
 Component{id:editorComponent;NetworkProfileEditor{entry:root.fixtures[root.index]}}
 Timer {
  interval:400;running:true;repeat:true
  onTriggered:{
   if(!editor.item)return;
   if(root.phase===0){
    NetworkControl.state=Object.assign({},NetworkControl.state,{profiles:[{id:"profile-a",name:"First",kind:"802-3-ethernet"},{id:"profile-b",name:"Active",kind:"802-3-ethernet"}]});
    if(card.selectedProfile?.id!=="profile-b"){root.fail("active profile selection");return;}
    root.find(card,"configure-network-interface").click();
    if(NetworkControl.editingUuid!=="profile-b"||NetworkControl.editingDevice!=="fixture-device"){root.fail("configure context");return;}
    root.fixtureDevice=Object.assign({},root.fixtureDevice,{active:""});card.selectedUuid="profile-a";
    if(card.selectedProfile?.id!=="profile-a"){root.fail("disconnected selection");return;}
    editor.item.section="ipv4";root.find(editor.item,"ipv4-addresses").text="192.0.2.20/24";
    editor.item.section="ipv6";root.find(editor.item,"ipv6-addresses").text="2001:db8::20/64";
    editor.item.section="ipv4";
    if(root.find(editor.item,"ipv4-addresses").text!=="192.0.2.20/24"){root.fail("draft lost");return;}
    if(root.find(editor.item,"network-ipv6-editor").changes().addresses[0]!=="2001:db8::20/64"){root.fail("families mixed");return;}
    const image=Quickshell.env("DOTS_TEST_EDITOR_IMAGE");if(image)body.grabToImage(result=>result.saveToFile(image));
   }else{
    const control=root.find(editor.item,"network-vpn-editor");
    if(!control||Object.keys(control.changes()).length){root.fail("VPN form changed initial values: "+JSON.stringify(control?.changes()));return;}
    console.log("VPN_EDITOR_OK",root.index);
   }
   root.phase++;
   if(root.phase===4){console.log("NETWORK_EDITOR_OK");Qt.quit();return;}
   editor.sourceComponent=null;root.index++;editor.sourceComponent=editorComponent;
  }
 }
 Timer{interval:15000;running:true;onTriggered:{root.fail("timeout");}}
}'''
            (base/'shell.qml').write_text(text.replace('__FIXTURES__',json.dumps(fixtures)))
            env=dict(os.environ,DOTS_SHELL_SOURCE=str(base),XDG_CONFIG_HOME=str(base/'config'),XDG_STATE_HOME=str(base/'state'),XDG_CACHE_HOME=str(base/'cache'))
            launcher=env.get('DOTS_TEST_LAUNCHER')
            result=subprocess.run([launcher] if launcher else [shutil.which('quickshell'),'-p',str(base)],env=env,capture_output=True,text=True,timeout=20)
            logs=result.stdout+result.stderr
            self.assertEqual(result.returncode,0,logs);self.assertIn('NETWORK_EDITOR_OK',logs)
            for failure in ('TypeError:','ReferenceError:','Cannot assign','Binding loop','Unable to assign','EDITOR_FAILED'):self.assertNotIn(failure,logs)

    def test_read_only_startup_profile_editor_and_creator(self):
        with tempfile.TemporaryDirectory(prefix='ai-network-panel-') as temporary:
            base=Path(temporary)
            for name in ('modules','services','assets','scripts','defaults','translations','GlobalStates.qml'):(base/name).symlink_to(SOURCE/name,target_is_directory=(SOURCE/name).is_dir())
            (base/'shell.qml').write_text('''//@ pragma UseQApplication
import QtQuick
import Quickshell
import Quickshell.Wayland
import qs.services
import qs.modules.shared
import qs.modules.desktop.network
ShellRoot {
 id:root
 property int phase:0
 function findChild(item,name){if(item.objectName===name)return item;for(const child of item.children||[]){const found=findChild(child,name);if(found)return found;}return null;}
 PanelWindow {
  implicitWidth:1000;implicitHeight:850;exclusiveZone:0;color:Appearance.colors.colLayer0
  WlrLayershell.namespace:"quickshell:network-test";WlrLayershell.keyboardFocus:WlrKeyboardFocus.None
  mask:Region{}
  NetworkPanelContent{id:panel;anchors.fill:parent;anchors.margins:20}
 }
 Component.onCompleted:NetworkControl.open()
 Timer {
  interval:400;running:true;repeat:true
  onTriggered:{
   if(!NetworkControl.loaded)return;
   if(NetworkControl.failed){console.error("NETWORK_FAILED",NetworkControl.message);Qt.quit();return;}
   if(root.phase===0){NetworkControl.page="wifi";NetworkControl.state=Object.assign({},NetworkControl.state,{scanning:["/device/test"]});Qt.callLater(()=>{const indicator=root.findChild(panel,"networkScanIndicator");console.log("NETWORK_SCAN_GEOMETRY",indicator?.active,indicator?.height,indicator?.visible);if(indicator?.active&&indicator?.visible&&indicator?.height>0)console.log("NETWORK_SCAN_VISIBLE");const image=Quickshell.env("DOTS_TEST_SCAN_IMAGE");if(image)panel.grabToImage(result=>result.saveToFile(image));});root.phase++;}
   else if(root.phase===1){NetworkControl.state=Object.assign({},NetworkControl.state,{scanning:[]});NetworkControl.page="profiles";if(NetworkControl.profiles.length)NetworkControl.edit(NetworkControl.profiles[0]);root.phase++;}
   else if(root.phase===2){if(NetworkControl.editingUuid&&!NetworkControl.editor.uuid)return;root.phase++;}
   else if(root.phase===3){NetworkControl.editor={};NetworkControl.creator={kind:"wifi",ssid:"Test"};root.phase++;}
   else if(root.phase===4){NetworkControl.creator={};NetworkControl.page="devices";const image=Quickshell.env("DOTS_TEST_NETWORK_IMAGE");if(image)panel.grabToImage(result=>result.saveToFile(image));root.phase++;}
   else{NetworkControl.close();console.log("NETWORK_PANEL_OK");Qt.quit();}
  }
 }
 Timer{interval:15000;running:true;onTriggered:{console.error("NETWORK_TIMEOUT",NetworkControl.message);Qt.quit();}}
}''')
            env=dict(os.environ,DOTS_SHELL_SOURCE=str(base),XDG_CONFIG_HOME=str(base/'config'),XDG_STATE_HOME=str(base/'state'),XDG_CACHE_HOME=str(base/'cache'))
            launcher=env.get('DOTS_TEST_LAUNCHER');command=[launcher] if launcher else [shutil.which('quickshell'),'-p',str(base)]
            result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=20)
            logs=result.stdout+result.stderr
            self.assertEqual(result.returncode,0,logs);self.assertIn('NETWORK_PANEL_OK',logs);self.assertIn('NETWORK_SCAN_VISIBLE',logs)
            for failure in ('TypeError:','ReferenceError:','Cannot assign','Binding loop','Unable to assign','Required property'):self.assertNotIn(failure,logs)
