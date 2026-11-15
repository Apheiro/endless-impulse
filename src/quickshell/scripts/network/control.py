#!/usr/bin/env python3
"""Event-driven libnm client and scoped secret agent. JSON lines, no CLI passwords."""
import ipaddress
import base64
import binascii
import json
import os
from pathlib import Path
import re
import signal
import socket
import sys
import time
import warnings
import tempfile
import uuid
import gi
gi.require_version('NM', '1.0')
from gi.repository import NM, Gio, GLib, GLibUnix, GObject

AGENT_PATH='/org/freedesktop/NetworkManager/SecretAgent'
SECRET_XML='''<node><interface name="org.freedesktop.NetworkManager.SecretAgent">
<method name="GetSecrets"><arg type="a{sa{sv}}" direction="in"/><arg type="o" direction="in"/><arg type="s" direction="in"/><arg type="as" direction="in"/><arg type="u" direction="in"/><arg type="a{sa{sv}}" direction="out"/></method>
<method name="CancelGetSecrets"><arg type="o" direction="in"/><arg type="s" direction="in"/></method>
<method name="SaveSecrets"><arg type="a{sa{sv}}" direction="in"/><arg type="o" direction="in"/></method>
<method name="DeleteSecrets"><arg type="a{sa{sv}}" direction="in"/><arg type="o" direction="in"/></method>
</interface></node>'''
SECRETS_IFACE='org.freedesktop.NetworkManager.SecretAgent'
AP_SECURITY=getattr(NM,'80211ApSecurityFlags')
AP_FLAGS=getattr(NM,'80211ApFlags')
SECRET_FIELDS={'802-11-wireless-security':['psk'], '802-1x':['password'], 'vpn':['password'],
               'gsm':['password','pin'], 'cdma':['password'], 'pppoe':['password'], 'wireguard':['private-key']}


def nickname(value): return getattr(value,'value_nick',str(value))
def ssid_text(value): return NM.utils_ssid_to_utf8(value.get_data()) if value else ''

def security(ap):
    flags=int(ap.get_rsn_flags())|int(ap.get_wpa_flags())
    if flags & int(AP_SECURITY.KEY_MGMT_802_1X|AP_SECURITY.KEY_MGMT_EAP_SUITE_B_192): return 'enterprise'
    if flags & int(AP_SECURITY.KEY_MGMT_SAE): return 'sae'
    if flags & int(AP_SECURITY.KEY_MGMT_PSK): return 'wpa-psk'
    if flags & int(AP_SECURITY.KEY_MGMT_OWE|AP_SECURITY.KEY_MGMT_OWE_TM): return 'owe'
    return 'wep' if int(ap.get_flags()) & int(AP_FLAGS.PRIVACY) else 'open'


def encode_nested(value):
    signature=value.get_type_string()
    if signature=='v':
        inner=value.get_variant()
        return {'$type':inner.get_type_string(),'$value':encode_nested(inner)}
    if signature.startswith('a{'):
        return {value.get_child_value(i).get_child_value(0).unpack():encode_nested(value.get_child_value(i).get_child_value(1)) for i in range(value.n_children())}
    if value.is_container():return [encode_nested(value.get_child_value(i)) for i in range(value.n_children())]
    return value.unpack()


def decode_nested(value):
    if isinstance(value,dict):
        if set(value)=={'$type','$value'}:return GLib.Variant(value['$type'],decode_nested(value['$value']))
        return {key:decode_nested(item) for key,item in value.items()}
    if isinstance(value,list):return [decode_nested(item) for item in value]
    return value


def typed_document(connection):
    variant=connection.to_dbus(NM.ConnectionSerializationFlags.NO_SECRETS)
    result={}
    for index in range(variant.n_children()):
        section=variant.get_child_value(index)
        name=section.get_child_value(0).get_string();settings=section.get_child_value(1)
        result[name]={}
        for key in settings.unpack():
            value=settings.lookup_value(key,None)
            result[name][key]={'type':value.get_type_string(),'value':encode_nested(value)}
    return result


def from_document(document):
    if not isinstance(document,dict) or len(document)>128:raise ValueError('Invalid NetworkManager settings document.')
    result={}
    for section,settings in document.items():
        if not isinstance(settings,dict):raise ValueError('Each setting must contain typed properties.')
        result[section]={}
        for name,field in settings.items():
            if not isinstance(field,dict) or set(field)!={'type','value'}:raise ValueError('Properties require type and value.')
            signature=field['type']
            if not isinstance(signature,str) or len(signature)>128 or not GLib.VariantType.string_is_valid(signature) or signature in ('v','h'):raise ValueError('Invalid property type.')
            result[section][name]=GLib.Variant(signature,decode_nested(field['value']))
    connection=NM.SimpleConnection.new_from_dbus(GLib.Variant('a{sa{sv}}',result))
    connection.verify()
    return connection


def create_profile(payload, interface=None):
    name=payload.get('name','').strip()
    if not name or len(name)>128: raise ValueError('Enter a profile name (up to 128 characters).')
    kind=payload.get('kind','wifi')
    types={'wifi':'802-11-wireless','hotspot':'802-11-wireless','ethernet':'802-3-ethernet','wireguard':'wireguard','vpn':'vpn','vlan':'vlan','bridge':'bridge','bond':'bond','pppoe':'pppoe'}
    if kind not in types: raise ValueError('Unsupported profile type; use a NetworkManager keyfile to import other types.')
    connection=NM.SimpleConnection.new()
    basic=NM.SettingConnection.new();basic.props.id=name;basic.props.uuid=str(uuid.uuid4());basic.props.type=types[kind]
    basic.props.autoconnect=bool(payload.get('autoconnect',False))
    if interface or payload.get("interfaceName"): basic.props.interface_name=interface or payload["interfaceName"]
    basic.add_permission('user',__import__('getpass').getuser(),None)
    connection.add_setting(basic)
    if kind in ('wifi','hotspot'):
        wifi=NM.SettingWireless.new()
        if payload.get('ssidHex'):
            try: raw=bytes.fromhex(payload['ssidHex'])
            except ValueError: raise ValueError('Invalid Wi-Fi SSID.')
        else: raw=payload.get('ssid','').encode('utf-8')
        if not 1<=len(raw)<=32: raise ValueError('Wi-Fi SSIDs must contain 1–32 bytes.')
        wifi.props.ssid=GLib.Bytes.new(raw)
        wifi.props.mode='ap' if kind=='hotspot' else 'infrastructure';wifi.props.hidden=bool(payload.get('hidden',False))
        connection.add_setting(wifi)
        mode=payload.get('security','wpa-psk')
        if mode!='open':
            secure=NM.SettingWirelessSecurity.new()
            secure.props.key_mgmt={'enterprise':'wpa-eap','sae':'sae','owe':'owe','wpa-psk':'wpa-psk','wep':'none'}.get(mode,'')
            if not secure.props.key_mgmt: raise ValueError('Unknown Wi-Fi security type.')
            password=payload.get('password','')
            if mode=='wpa-psk' and password and not (8<=len(password.encode())<=63 or re.fullmatch('[0-9a-fA-F]{64}',password)):
                raise ValueError('WPA passwords need 8–63 bytes or 64 hexadecimal digits.')
            if mode in ('wpa-psk','sae'):
                if kind=='hotspot' and not password: raise ValueError('Set a password for the hotspot.')
                if password:secure.props.psk=password
                secure.props.psk_flags=NM.SettingSecretFlags.NONE if payload.get('remember',True) else NM.SettingSecretFlags.NOT_SAVED
            if mode=='wep':
                secure.props.wep_key0=password;secure.props.wep_key_type=NM.WepKeyType.KEY if len(password) in (5,10,13,26) else NM.WepKeyType.PASSPHRASE
                secure.props.wep_key_flags=NM.SettingSecretFlags.NONE if payload.get('remember',True) else NM.SettingSecretFlags.NOT_SAVED
            connection.add_setting(secure)
            if mode=='enterprise':
                enterprise=NM.Setting8021x.new()
                method=payload.get('eap','peap')
                if method not in ('peap','ttls','tls'): raise ValueError('Choose PEAP, TTLS or TLS.')
                enterprise.add_eap_method(method)
                enterprise.props.identity=payload.get('identity','')
                if not enterprise.props.identity:raise ValueError('Enter the enterprise identity.')
                if method!='tls':enterprise.props.phase2_auth=payload.get('phase2','mschapv2')
                enterprise.props.password_flags=NM.SettingSecretFlags.NONE if payload.get('remember',True) else NM.SettingSecretFlags.NOT_SAVED
                if password:enterprise.props.password=password
                domain=payload.get('domain','').strip()
                if domain:enterprise.props.domain_suffix_match=domain
                ca=payload.get('ca','').strip()
                if not ca and not payload.get('systemCa',True): raise ValueError('Choose a CA certificate or use system certificates.')
                if ca:enterprise.set_ca_cert(ca,NM.Setting8021xCKScheme.PATH)
                else:enterprise.props.system_ca_certs=True
                if method=='tls':
                    if not payload.get('clientCert') or not payload.get('privateKey'):raise ValueError('TLS needs a client certificate and private key.')
                    enterprise.set_client_cert(payload['clientCert'],NM.Setting8021xCKScheme.PATH)
                    enterprise.set_private_key(payload['privateKey'],payload.get('keyPassword') or None,NM.Setting8021xCKScheme.PATH)
                connection.add_setting(enterprise)
    elif kind=='ethernet':connection.add_setting(NM.SettingWired.new())
    elif kind=='wireguard':connection.add_setting(NM.SettingWireGuard.new())
    elif kind=='vpn':
        setting=NM.SettingVpn.new();setting.props.service_type=payload.get('service','org.freedesktop.NetworkManager.openvpn');connection.add_setting(setting)
    elif kind=='vlan':
        setting=NM.SettingVlan.new();setting.props.id=int(payload.get('vlan',1));setting.props.parent=payload.get('parent','');connection.add_setting(setting)
    elif kind=='bridge':connection.add_setting(NM.SettingBridge.new())
    elif kind=='bond':connection.add_setting(NM.SettingBond.new())
    elif kind=='pppoe':
        setting=NM.SettingPppoe.new();setting.props.username=payload.get('identity','');setting.props.password=payload.get('password') or None;connection.add_setting(setting)
    ip4=NM.SettingIP4Config.new();ip4.props.method='shared' if kind=='hotspot' else 'disabled' if kind=='wireguard' else 'auto';connection.add_setting(ip4)
    ip6=NM.SettingIP6Config.new();ip6.props.method='disabled' if kind in ('hotspot','wireguard') else 'auto';connection.add_setting(ip6)
    connection.normalize()
    connection.verify()
    return connection


def vpn_services():
    services={info.get_service() for info in NM.VpnPluginInfo.list_load()}
    # The pinned client may not share the host daemon's plugin directory.
    for folder in ('/usr/lib/NetworkManager/VPN','/usr/lib64/NetworkManager/VPN','/etc/NetworkManager/VPN'):
        for path in Path(folder).glob('*.name'):
            try:
                data=GLib.KeyFile.new();data.load_from_file(str(path),GLib.KeyFileFlags.NONE)
                services.add(data.get_string('VPN Connection','service'))
            except GLib.Error:continue
    return services


def wireguard_key(value):
    try:valid=len(base64.b64decode(value,validate=True))==32
    except (ValueError,binascii.Error):valid=False
    if not valid:raise ValueError('WireGuard keys must be base64-encoded 32-byte keys.')
    return value


def edit_vpn_settings(clone,payload):
    if 'vpn' in payload:
        vpn=clone.get_setting_vpn()
        if not vpn:raise ValueError('This profile is not a VPN plugin connection.')
        update=payload['vpn']
        for key,value in update.get('data',{}).items():
            if not isinstance(key,str) or not key or any(c in key for c in '\n\r\x00') or not isinstance(value,str) or '\x00' in value:raise ValueError('VPN properties require valid names and string values.')
            if vpn.props.service_type=='org.freedesktop.NetworkManager.openvpn':
                if key=='port' and value and not 1<=int(value)<=65535:raise ValueError('OpenVPN port must be 1–65535.')
                if key=='connection-type' and value not in ('tls','password','password-tls','static-key'):raise ValueError('Choose a valid OpenVPN authentication method.')
                if key=='remote' and not value.strip():raise ValueError('Enter an OpenVPN server.')
            if value:vpn.add_data_item(key,value)
            else:vpn.remove_data_item(key)
        if vpn.props.service_type=='org.freedesktop.NetworkManager.openvpn' and vpn.get_data_item('remote') and not vpn.get_data_item('connection-type'):vpn.add_data_item('connection-type','tls')
        for key,value in update.get('secrets',{}).items():
            if not isinstance(key,str) or not key or not isinstance(value,str):raise ValueError('Invalid VPN credential.')
            if value:vpn.add_secret(key,value);vpn.set_secret_flags(key,NM.SettingSecretFlags.NONE)
    if 'wireguard' in payload:
        wg=clone.get_setting_by_name('wireguard')
        if not wg:raise ValueError('This profile is not a WireGuard connection.')
        data=payload['wireguard']
        if data.get('privateKey'):wg.props.private_key=wireguard_key(data['privateKey']);wg.props.private_key_flags=NM.SettingSecretFlags.NONE
        if 'listenPort' in data:
            port=int(data['listenPort'])
            if not 0<=port<=65535:raise ValueError('Listen port must be 0–65535.')
            wg.props.listen_port=port
        if 'peerRoutes' in data:wg.props.peer_routes=bool(data['peerRoutes'])
        if 'peers' in data:
            existing={wg.get_peer(i).get_public_key():wg.get_peer(i) for i in range(wg.get_peers_len())}
            peers=[];identities=set()
            for row in data['peers']:
                public=wireguard_key(row['publicKey'])
                if public in identities:raise ValueError('WireGuard peer public keys must be unique.')
                identities.add(public)
                peer=NM.WireGuardPeer.new();peer.set_public_key(public,False)
                previous=existing.get(public)
                if previous:
                    peer.set_preshared_key_flags(previous.get_preshared_key_flags())
                    if previous.get_preshared_key():peer.set_preshared_key(previous.get_preshared_key(),False)
                if row.get('presharedKey'):peer.set_preshared_key(wireguard_key(row['presharedKey']),False);peer.set_preshared_key_flags(NM.SettingSecretFlags.NONE)
                endpoint=row.get('endpoint','').strip()
                if endpoint and not peer.set_endpoint(endpoint,False):raise ValueError('WireGuard endpoints use host:port or [IPv6]:port.')
                for address in row.get('allowedIps',[]):
                    network=ipaddress.ip_network(address,strict=False)
                    if not peer.append_allowed_ip(str(network),False):raise ValueError('Invalid WireGuard allowed network.')
                keepalive=int(row.get('keepalive',0))
                if not 0<=keepalive<=65535:raise ValueError('Keepalive must be 0–65535 seconds.')
                peer.set_persistent_keepalive(keepalive)
                peer.is_valid(True,True);peers.append(peer)
            wg.clear_peers()
            for peer in peers:wg.append_peer(peer)


def edit_profile(connection, payload):
    clone=NM.SimpleConnection.new_clone(connection)
    basic=clone.get_setting_connection()
    if payload.get('name','').strip():basic.props.id=payload['name'].strip()
    basic.props.autoconnect=bool(payload.get('autoconnect',basic.props.autoconnect))
    if "metered" in payload:basic.props.metered=NM.Metered.YES if payload["metered"] else NM.Metered.NO
    for family,key,setting_class in ((socket.AF_INET,'ipv4',NM.SettingIP4Config),(socket.AF_INET6,'ipv6',NM.SettingIP6Config)):
        data=payload.get(key)
        if data is None:continue
        setting=clone.get_setting_by_name(key)
        if not setting:setting=setting_class.new();clone.add_setting(setting)
        mode=data.get('method',setting.props.method or 'auto')
        allowed=('auto','manual','link-local','shared','disabled') if family==socket.AF_INET else ('auto','manual','link-local','shared','disabled','dhcp','ignore')
        if mode not in allowed:raise ValueError('Invalid IP configuration method.')
        setting.props.method=mode
        if 'addresses' in data:
            setting.clear_addresses()
            for address in data['addresses']:
                value=ipaddress.ip_interface(address.strip())
                if value.version!=(4 if family==socket.AF_INET else 6):raise ValueError('Address family does not match.')
                setting.add_address(NM.IPAddress.new(family,str(value.ip),value.network.prefixlen))
        if mode=='manual' and not setting.get_num_addresses():raise ValueError('Manual configuration needs an address/prefix.')
        if 'gateway' in data:
            gateway=data['gateway'].strip()
            if gateway and ipaddress.ip_address(gateway).version!=(4 if family==socket.AF_INET else 6):raise ValueError('Invalid gateway family.')
            setting.props.gateway=gateway or None
        if 'dns' in data:
            setting.clear_dns()
            for address in data['dns']:
                address=address.strip()
                if ipaddress.ip_address(address).version!=(4 if family==socket.AF_INET else 6):raise ValueError('Invalid DNS family.')
                setting.add_dns(address)
        if 'domains' in data:
            setting.clear_dns_searches()
            for domain in data['domains']:
                if domain.strip():setting.add_dns_search(domain.strip())
        for key,prop in (('ignoreAutoDns','ignore_auto_dns'),('neverDefault','never_default')):
            if key in data:setting.set_property(prop,bool(data[key]))
        if 'metric' in data:setting.props.route_metric=int(data['metric'])
        if 'routes' in data:setting.clear_routes()
        for route in data.get('routes',[]):
            dest=ipaddress.ip_network(route['destination'],strict=False)
            if dest.version!=(4 if family==socket.AF_INET else 6):raise ValueError('Route family does not match.')
            hop=route.get('gateway') or None
            if hop and ipaddress.ip_address(hop).version!=dest.version:raise ValueError('Route gateway family does not match.')
            setting.add_route(NM.IPRoute.new(family,str(dest.network_address),dest.prefixlen,hop,int(route.get('metric',-1))))
        if mode in ('disabled','ignore'):
            setting.clear_addresses();setting.clear_dns();setting.clear_dns_searches();setting.clear_routes();setting.props.gateway=None
    for name in ('802-3-ethernet','802-11-wireless'):
        setting=clone.get_setting_by_name(name)
        if setting and 'mtu' in payload:
            mtu=int(payload['mtu'])
            if not (mtu==0 or 68<=mtu<=65535):raise ValueError('MTU must be 0 (automatic) or 68–65535.')
            setting.props.mtu=mtu
        if setting and 'mac' in payload:setting.props.cloned_mac_address=payload['mac'].strip() or None
    if payload.get('password'):
        secure=clone.get_setting_wireless_security()
        enterprise=clone.get_setting_802_1x()
        ppp=clone.get_setting_pppoe()
        if enterprise:enterprise.props.password=payload['password']
        elif secure and secure.props.key_mgmt in ('wpa-psk','sae'):secure.props.psk=payload['password']
        elif ppp:ppp.props.password=payload['password']
        else:raise ValueError('Use the typed editor for this credential type.')
    edit_vpn_settings(clone,payload)
    clone.verify()
    return clone


def profile_settings(connection):
    basic=connection.get_setting_connection()
    data=dict(name=basic.props.id,kind=connection.get_connection_type(),autoconnect=basic.props.autoconnect,metered=basic.props.metered==NM.Metered.YES)
    for name in ('ipv4','ipv6'):
        setting=connection.get_setting_by_name(name)
        if setting:data[name]=dict(method=setting.props.method,addresses=[f'{setting.get_address(i).get_address()}/{setting.get_address(i).get_prefix()}' for i in range(setting.get_num_addresses())],gateway=setting.props.gateway or '',dns=[setting.get_dns(i) for i in range(setting.get_num_dns())],domains=[setting.get_dns_search(i) for i in range(setting.get_num_dns_searches())],ignoreAutoDns=setting.props.ignore_auto_dns,neverDefault=setting.props.never_default,metric=setting.props.route_metric,routes=[dict(destination=f'{setting.get_route(i).get_dest()}/{setting.get_route(i).get_prefix()}',gateway=setting.get_route(i).get_next_hop() or '',metric=setting.get_route(i).get_metric()) for i in range(setting.get_num_routes())])
    vpn=connection.get_setting_vpn()
    if vpn:data['vpn']=dict(service=vpn.props.service_type,available=vpn.props.service_type in vpn_services(),data={key:vpn.get_data_item(key) for key in vpn.get_data_keys() or []})
    wg=connection.get_setting_by_name('wireguard')
    if wg:data['wireguard']=dict(listenPort=wg.props.listen_port,peerRoutes=wg.props.peer_routes,peers=[dict(publicKey=wg.get_peer(i).get_public_key(),endpoint=wg.get_peer(i).get_endpoint() or '',allowedIps=[wg.get_peer(i).get_allowed_ip(j) for j in range(wg.get_peer(i).get_allowed_ips_len())],keepalive=wg.get_peer(i).get_persistent_keepalive()) for i in range(wg.get_peers_len())])
    secure=connection.get_setting_wireless_security()
    data['passwordEditable']=bool(connection.get_setting_pppoe() or connection.get_setting_802_1x() or secure and secure.props.key_mgmt in ('wpa-psk','sae'))
    link=connection.get_setting_wired() or connection.get_setting_wireless()
    if link:data.update(mtu=link.props.mtu,mac=link.props.cloned_mac_address or '')
    return data


def setting_schema():
    result=[]
    for name in dir(NM):
        cls=getattr(NM,name)
        if not name.startswith('Setting') or not isinstance(cls,type) or not issubclass(cls,NM.Setting) or cls is NM.Setting:continue
        if GObject.type_test_flags(cls.__gtype__,GObject.TypeFlags.ABSTRACT):continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore",DeprecationWarning);setting=cls.new()
            properties=[]
            for prop in setting.list_properties():
                signature=setting.get_dbus_property_type(prop.name)
                if signature and prop.flags & GObject.ParamFlags.WRITABLE:
                    properties.append(dict(name=prop.name,type=signature.dup_string(),description=prop.blurb or '',secret=bool(int(prop.flags)&int(NM.SETTING_PARAM_SECRET))))
            result.append(dict(name=setting.get_name(),properties=properties))
        except (TypeError,AttributeError):pass
    return result


def import_profile(path):
    path=Path(path).expanduser()
    if not path.is_file() or path.stat().st_size>4*1024*1024:raise ValueError('Choose a connection file smaller than 4 MB.')
    if path.suffix=='.json':return from_document(json.loads(path.read_text()))
    keyfile=GLib.KeyFile.new()
    try:keyfile.load_from_file(str(path),GLib.KeyFileFlags.NONE)
    except GLib.Error:pass
    if keyfile.has_group('connection'):return NM.keyfile_read(keyfile,str(path.parent),NM.KeyfileHandlerFlags.NONE,None,None)
    if keyfile.has_group('Interface'):return NM.conn_wireguard_import(str(path))
    for info in NM.VpnPluginInfo.list_load():
        try:
            plugin=info.load_editor_plugin()
            if plugin:
                profile=plugin.import_(str(path))
                if profile:return profile
        except GLib.Error:continue
    raise ValueError('No compatible VPN importer is installed. Install its NetworkManager plugin or import a NetworkManager keyfile.')


class SecretAgent:
    def __init__(self, controller):
        self.controller=controller;self.bus=controller.client.get_dbus_connection();self.pending=None
        self.registered=False;self.registering=False
        self.bus.register_object(AGENT_PATH,Gio.DBusNodeInfo.new_for_xml(SECRET_XML).interfaces[0],self.method,None,None)
    def enable(self):
        if self.registered or self.registering:return
        self.registering=True
        self.bus.call('org.freedesktop.NetworkManager','/org/freedesktop/NetworkManager/AgentManager','org.freedesktop.NetworkManager.AgentManager','RegisterWithCapabilities',GLib.Variant('(su)',('org.EndlessImpulse.Network.p'+str(os.getpid()),0)),None,Gio.DBusCallFlags.NONE,10000,None,self.registered_done)
    def registered_done(self,connection,result):
        self.registering=False
        try:connection.call_finish(result);self.registered=True;self.controller.emit(dict(event='agent',ok=True))
        except GLib.Error as error:self.controller.emit(dict(event='agent',ok=False,error=error.message))
    def cancel(self):
        if self.pending:
            self.pending['invocation'].return_dbus_error(SECRETS_IFACE+'.UserCanceled','Canceled by the user.');self.pending=None
        self.controller.emit(dict(event='prompt',prompt={}))
    def method(self,connection,sender,path,interface,method,parameters,invocation):
        if sender!=self.controller.client.get_dbus_name_owner():
            invocation.return_dbus_error(SECRETS_IFACE+'.UserCanceled','Only NetworkManager may request secrets.');return
        args=parameters.unpack()
        if method=='CancelGetSecrets':
            if self.pending and (self.pending['path'],self.pending['setting'])==tuple(args):self.cancel()
            invocation.return_value(GLib.Variant('()',()));return
        if method=='SaveSecrets':
            invocation.return_dbus_error(SECRETS_IFACE+'.NoSecrets','Shell credentials are session-only; persistent storage is owned by NetworkManager.');return
        if method=='DeleteSecrets':invocation.return_value(GLib.Variant('()',()));return
        settings,connection_path,setting,hints,flags=args
        identity=settings.get('connection',{}).get('uuid','')
        if identity not in self.controller.owned or not self.controller.panel_open or not flags & 1:
            invocation.return_dbus_error(SECRETS_IFACE+'.NoSecrets','Not an interactive connection started by this panel.');return
        if self.pending:
            invocation.return_dbus_error(SECRETS_IFACE+'.UserCanceled','Another request is active.');return
        fields=[value for value in hints if not value.startswith('x-vpn-message:')] or SECRET_FIELDS.get(setting,['password'])
        if setting=='802-11-wireless-security' and settings.get(setting,{}).get('key-mgmt')=='none':fields=['wep-key0']
        fields=list(dict.fromkeys(fields))
        token=uuid.uuid4().hex
        self.pending=dict(id=token,invocation=invocation,setting=setting,fields=fields,uuid=identity,path=connection_path)
        self.controller.emit(dict(event='prompt',prompt=dict(id=token,name=settings.get('connection',{}).get('id',''),setting=setting,fields=fields)))
    def respond(self,payload):
        pending=self.pending
        if not pending or pending['id']!=payload.get('prompt'):raise ValueError('This password request is no longer active.')
        if not payload.get('accept'):self.cancel();return
        values=payload.get('values',{})
        if any(not isinstance(values.get(name),str) or not values[name] for name in pending['fields']):raise ValueError('Complete the requested credentials.')
        data={name:GLib.Variant('s',values[name]) for name in pending['fields']}
        if pending['setting']=='vpn':data={'secrets':GLib.Variant('a{ss}',{name:values[name] for name in pending['fields']})}
        pending['invocation'].return_value(GLib.Variant('(a{sa{sv}})',({pending['setting']:data},)))
        self.pending=None;self.controller.emit(dict(event='prompt',prompt={}))


class Controller:
    def __init__(self, client, emit):
        self.client=client;self.emit=emit;self.owned=set();self.panel_open=False;self.agent=SecretAgent(self)
        self.watched={};self.refresh_id=0;self.checkpoint=None;self.checkpoint_pending=False;self.active_requests={}
        self.radio_generation=0;self.enable_scan_timer=0;self.enable_scan_deadline=0;self.enable_scan_pending=set();self.enable_scan_running=set();self.scan_watches={}
        client.connect('notify',self.changed)
        for name in ('device-added','device-removed','connection-added','connection-removed','active-connection-added','active-connection-removed'):client.connect(name,self.changed)
        self.snapshot()
    def changed(self,*_):
        if not self.client.get_nm_running():self.agent.registered=False;self.agent.cancel()
        elif self.panel_open:self.agent.enable()
        if not self.refresh_id:self.refresh_id=GLib.timeout_add(180,self.snapshot)
    def watch(self,obj):
        if obj and obj not in self.watched:
            self.watched[obj]=[obj.connect('notify',self.changed)]
            for signal in ('changed','access-point-added','access-point-removed'):
                if GObject.signal_lookup(signal,obj.__gtype__):self.watched[obj].append(obj.connect(signal,self.changed))
    def done(self,payload,error=None,**data):
        self.emit(dict(event='result',id=payload.get('id',''),ok=not error,error=error or '',**data));self.changed()
    def device(self,payload):
        device=next((d for d in self.client.get_devices() if d.get_path()==payload.get('device')),None)
        if not device or payload.get('interface',device.get_iface())!=device.get_iface():raise ValueError('This network interface changed or disappeared.')
        return device
    def profile(self,payload):
        profile=self.client.get_connection_by_uuid(payload.get('uuid',''))
        if not profile:raise ValueError('This connection profile no longer exists.')
        return profile
    def finish(self,payload,finisher,after=None):
        def callback(source,result):
            try:
                value=finisher(result)
                if after:after(value)
                else:self.done(payload)
            except (GLib.Error,ValueError,TypeError) as error:self.done(payload,str(error))
        return callback
    def protect(self,device,payload,action):
        if self.checkpoint or self.checkpoint_pending:raise ValueError('Keep or revert the previous connection test first.')
        if not device or not device.get_active_connection():action();return
        self.checkpoint_pending=True
        def created(source,result):
            self.checkpoint_pending=False
            try:
                checkpoint=self.client.checkpoint_create_finish(result)
                self.checkpoint=dict(path=checkpoint.get_path(),expires=time.time()+45)
                self.changed();action()
            except (GLib.Error,ValueError,TypeError) as error:self.done(payload,str(error))
        self.client.checkpoint_create([device],45,NM.CheckpointCreateFlags.NONE,None,created)
    def activate(self,payload,profile,device,ap=None,new=False):
        identity=profile.get_uuid();self.owned.add(identity)
        def activated(source,result):
            try:
                connection=self.client.add_and_activate_connection2_finish(result)[0] if new else self.client.activate_connection_finish(result)
                timer=GLib.timeout_add_seconds(90,lambda:self.activation_end(payload,connection,identity,'The connection timed out.'))
                self.active_requests[payload['id']]=(connection,timer,identity)
                connection.connect('state-changed',lambda *_:self.activation_state(payload,connection,identity))
                self.activation_state(payload,connection,identity)
            except GLib.Error as error:
                self.owned.discard(identity);self.done(payload,error.message)
                if self.checkpoint:self.rollback()
        if new:self.client.add_and_activate_connection2(profile,device,ap,GLib.Variant('a{sv}',{'persist':GLib.Variant('s','disk')}),None,activated)
        else:self.client.activate_connection_async(profile,device,ap,None,activated)
    def activation_state(self,payload,connection,identity):
        if payload['id'] not in self.active_requests:return
        if connection.get_state()==NM.ActiveConnectionState.ACTIVATED:self.activation_end(payload,connection,identity)
        elif connection.get_state()==NM.ActiveConnectionState.DEACTIVATED:self.activation_end(payload,connection,identity,'Connection failed: '+nickname(connection.get_state_reason()))
    def activation_end(self,payload,connection,identity,error=None):
        request=self.active_requests.pop(payload['id'],None)
        if not request:return False
        if request[1]:GLib.source_remove(request[1])
        self.owned.discard(identity)
        if self.agent.pending and self.agent.pending['uuid']==identity:self.agent.cancel()
        self.done(payload,error)
        if error:
            if self.checkpoint:self.rollback()
            elif connection.get_state()!=NM.ActiveConnectionState.DEACTIVATED:self.client.deactivate_connection_async(connection,None,lambda *_:None)
        return False
    def rollback(self,payload=None):
        if not self.checkpoint:
            if payload:self.done(payload)
            return
        path=self.checkpoint['path']
        def rolled(source,result):
            try:
                self.client.checkpoint_rollback_finish(result)
                self.client.checkpoint_destroy(path,None,self.finish(payload or {},self.client.checkpoint_destroy_finish))
            except GLib.Error as error:
                if payload:self.done(payload,error.message)
        self.client.checkpoint_rollback(path,None,rolled)

    def preserve_secrets(self,remote,clone,payload,callback):
        names=[name for name in SECRET_FIELDS if clone.get_setting_by_name(name)]
        supplied=clone.to_dbus(NM.ConnectionSerializationFlags.ONLY_SECRETS)
        def step():
            if not names:callback();return
            name=names.pop()
            def secrets(source,result):
                try:
                    secrets=remote.get_secrets_finish(result)
                    if secrets and name=='wireguard':
                        section=secrets.lookup_value('wireguard',None)
                        if section:
                            fields={key:section.lookup_value(key,None) for key in section.unpack()}
                            peers=fields.get('peers')
                            if peers:
                                wg=clone.get_setting_by_name('wireguard')
                                public_keys={wg.get_peer(i).get_public_key() for i in range(wg.get_peers_len())}
                                fields['peers']=GLib.Variant('aa{sv}',[{key:peer.lookup_value(key,None) for key in peer.unpack()} for peer in [peers.get_child_value(i) for i in range(peers.n_children())] if peer.lookup_value('public-key',None).get_string() in public_keys])
                            secrets=GLib.Variant('a{sa{sv}}',{'wireguard':fields})
                    if secrets:clone.update_secrets(name,secrets)
                    if supplied.lookup_value(name,None):clone.update_secrets(name,supplied)
                except (GLib.Error,ValueError,TypeError) as error:
                    # Updating a complete settings dictionary can delete daemon-owned secrets.
                    # Abort rather than guessing when the daemon denies retrieval.
                    self.done(payload,"Could not preserve this profile’s saved credentials: "+str(error));return
                step()
            remote.get_secrets_async(name,None,secrets)
        step()

    def end_scan_watch(self,path):
        watch=self.scan_watches.pop(path,None)
        if watch:
            GObject.signal_handler_disconnect(watch['device'],watch['handler'])
            GLib.source_remove(watch['timer'])
            self.changed()

    def begin_scan_watch(self,device):
        path=device.get_path()
        self.end_scan_watch(path)
        baseline=device.get_last_scan()
        def completed(*_):
            if device.get_last_scan()>baseline:self.end_scan_watch(path)
        def expired():
            # Also covers hardware removal or a daemon that never completes a scan.
            self.end_scan_watch(path);return False
        self.scan_watches[path]=dict(device=device,handler=device.connect('notify::last-scan',completed),timer=GLib.timeout_add_seconds(30,expired))
        self.changed()

    def cancel_enabled_scans(self):
        self.radio_generation+=1
        for path in list(self.scan_watches):self.end_scan_watch(path)
        if self.enable_scan_timer:GLib.source_remove(self.enable_scan_timer)
        self.enable_scan_timer=0;self.enable_scan_pending.clear();self.enable_scan_running.clear()

    def queue_enabled_scans(self):
        # The radio property can be acknowledged before the adapter is usable.
        self.enable_scan_pending={d.get_path() for d in self.client.get_devices() if isinstance(d,NM.DeviceWifi) and d.get_managed()}
        self.enable_scan_deadline=time.monotonic()+15
        if self.enable_scan_pending and not self.enable_scan_timer:
            self.enable_scan_timer=GLib.timeout_add_seconds(1,self.scan_enabled_wifi)
        self.scan_enabled_wifi();self.changed()

    def scan_enabled_wifi(self):
        if time.monotonic()>=self.enable_scan_deadline:
            if self.enable_scan_pending:self.emit(dict(event='scan-error',error='Automatic Wi-Fi search could not start. Try Scan again once the adapter is ready.'))
            self.enable_scan_pending.clear();self.changed()
        if not self.enable_scan_pending:
            self.enable_scan_timer=0;return False
        if not self.client.wireless_get_enabled():return True
        devices={d.get_path():d for d in self.client.get_devices() if isinstance(d,NM.DeviceWifi)}
        generation=self.radio_generation
        for path in list(self.enable_scan_pending-self.enable_scan_running):
            device=devices.get(path)
            if not device or not device.get_managed():self.enable_scan_pending.discard(path);continue
            if device.get_state() not in (NM.DeviceState.DISCONNECTED,NM.DeviceState.ACTIVATED):continue
            self.enable_scan_running.add(path)
            self.begin_scan_watch(device)
            def scanned(source,result,path=path,device=device):
                if generation!=self.radio_generation:return
                self.enable_scan_running.discard(path)
                try:device.request_scan_finish(result);self.enable_scan_pending.discard(path)
                except GLib.Error:self.end_scan_watch(path) # NetworkManager may still be waking the adapter; bounded retry.
                self.changed()
            device.request_scan_async(None,scanned)
        return True

    def snapshot(self):
        self.refresh_id=0
        devices=[];access_points=[];profiles=[];live=set()
        active={c.get_uuid():c for c in self.client.get_active_connections()}
        for device in self.client.get_devices():
            self.watch(device);live.add(device)
            kind=nickname(device.get_device_type())
            if kind=='loopback':continue
            item=dict(id=device.get_path(),interface=device.get_iface(),kind=kind,state=nickname(device.get_state()),reason=nickname(device.get_state_reason()),managed=device.get_managed(),hw=device.get_hw_address() or '',active=device.get_active_connection().get_uuid() if device.get_active_connection() else '',profiles=[c.get_uuid() for c in device.get_available_connections()])
            for family,getter in ((4,device.get_ip4_config),(6,device.get_ip6_config)):
                ip=getter();self.watch(ip)
                if ip:live.add(ip)
                item['ip'+str(family)]=dict(addresses=[f'{a.get_address()}/{a.get_prefix()}' for a in ip.get_addresses()],gateway=ip.get_gateway() or '',dns=ip.get_nameservers(),domains=ip.get_domains(),routes=[dict(destination=f'{r.get_dest()}/{r.get_prefix()}',gateway=r.get_next_hop() or '',metric=r.get_metric()) for r in ip.get_routes()]) if ip else {}
            if isinstance(device,NM.DeviceEthernet):item.update(carrier=device.get_carrier(),speed=device.get_speed())
            if isinstance(device,NM.DeviceWifi):
                item.update(hotspot=bool(device.get_capabilities() & NM.DeviceWifiCapabilities.AP),bitrate=device.get_bitrate())
                current=device.get_active_access_point()
                for ap in device.get_access_points():
                    self.watch(ap);live.add(ap)
                    raw=ap.get_ssid()
                    if not raw:continue
                    access_points.append(dict(id=ap.get_path(),device=device.get_path(),interface=device.get_iface(),ssid=ssid_text(raw),ssidHex=bytes(raw.get_data()).hex(),bssid=ap.get_bssid(),strength=ap.get_strength(),frequency=ap.get_frequency(),security=security(ap),active=ap==current,profiles=[c.get_uuid() for c in device.get_available_connections() if ap.connection_valid(c)]))
            devices.append(item)
        for profile in self.client.get_connections():
            self.watch(profile);live.add(profile)
            profiles.append(dict(id=profile.get_uuid(),name=profile.get_id(),kind=profile.get_connection_type(),active=profile.get_uuid() in active,interface=profile.get_interface_name() or '',autoconnect=profile.get_setting_connection().props.autoconnect))
        for connection in active.values():self.watch(connection);live.add(connection)
        for obj,handlers in list(self.watched.items()):
            if obj not in live:
                for handler in handlers:GObject.signal_handler_disconnect(obj,handler)
                del self.watched[obj]
        if self.checkpoint and not any(c.get_path()==self.checkpoint['path'] for c in self.client.get_checkpoints()):self.checkpoint=None
        self.emit(dict(event='state',state=dict(available=self.client.get_nm_running(),networking=self.client.networking_get_enabled(),wifiEnabled=self.client.wireless_get_enabled(),wifiHardware=self.client.wireless_hardware_get_enabled(),connectivity=nickname(self.client.get_connectivity()),primary=self.client.get_primary_connection().get_id() if self.client.get_primary_connection() else '',devices=devices,networks=access_points,profiles=profiles,checkpoint=self.checkpoint or {},scanning=list(self.enable_scan_pending|self.scan_watches.keys()))))
        return False
    def command(self,payload):
        operation=payload.get('action')
        if operation=='panel':
            self.panel_open=bool(payload.get('open'))
            if self.panel_open:self.agent.enable()
            else:
                self.agent.cancel()
                if self.checkpoint:self.rollback()
            self.done(payload);return
        if operation=='respond':self.agent.respond(payload);self.done(payload);return
        if operation=='refresh':self.snapshot();self.done(payload);return
        if operation=='schema':self.done(payload,schema=setting_schema());return
        if operation=='vpn-plugins':self.done(payload,vpnServices=sorted(vpn_services()));return
        if operation=='wifi':
            self.cancel_enabled_scans()
            generation=self.radio_generation
            bus=self.client.get_dbus_connection()
            def enabled(_):
                if payload['enabled'] and generation==self.radio_generation:self.queue_enabled_scans()
                self.done(payload)
            bus.call('org.freedesktop.NetworkManager','/org/freedesktop/NetworkManager','org.freedesktop.DBus.Properties','Set',GLib.Variant('(ssv)',('org.freedesktop.NetworkManager','WirelessEnabled',GLib.Variant('b',bool(payload['enabled'])))),None,Gio.DBusCallFlags.NONE,15000,None,self.finish(payload,bus.call_finish,enabled));return
        if operation=='networking':
            bus=self.client.get_dbus_connection()
            bus.call('org.freedesktop.NetworkManager','/org/freedesktop/NetworkManager','org.freedesktop.NetworkManager','Enable',GLib.Variant('(b)',(bool(payload['enabled']),)),None,Gio.DBusCallFlags.NONE,15000,None,self.finish(payload,bus.call_finish));return
        if operation=='connectivity':self.client.check_connectivity_async(None,self.finish(payload,self.client.check_connectivity_finish));return
        if operation=='keep':
            if not self.checkpoint:raise ValueError('No network test is active.')
            self.client.checkpoint_destroy(self.checkpoint['path'],None,self.finish(payload,self.client.checkpoint_destroy_finish));return
        if operation=='rollback':self.rollback(payload);return
        if operation=='scan':
            device=self.device(payload)
            if not isinstance(device,NM.DeviceWifi):raise ValueError('Choose a Wi-Fi interface.')
            self.begin_scan_watch(device)
            def scanned(source,result):
                try:device.request_scan_finish(result);self.done(payload)
                except GLib.Error as error:self.end_scan_watch(device.get_path());self.done(payload,error.message)
            device.request_scan_async(None,scanned);return
        if operation=='disconnect':
            device=self.device(payload)
            device.disconnect_async(None,self.finish(payload,device.disconnect_finish));return
        if operation in ('details','edit','advanced','delete','export','activate','clone'):
            profile=self.profile(payload)
            if operation=='details':self.done(payload,document=typed_document(profile),settings=profile_settings(profile),version=profile.get_version_id());return
            if operation=='clone':
                clone=NM.SimpleConnection.new_from_dbus(profile.to_dbus(NM.ConnectionSerializationFlags.NO_SECRETS));clone.get_setting_connection().props.uuid=str(uuid.uuid4());clone.get_setting_connection().props.id=profile.get_id()+' (copy)';clone.get_setting_connection().props.autoconnect=False
                self.client.add_connection2(clone.to_dbus(NM.ConnectionSerializationFlags.ALL),NM.SettingsAddConnection2Flags.TO_DISK,None,True,None,self.finish(payload,self.client.add_connection2_finish));return
            if operation=='delete':
                if profile.get_uuid() in {c.get_uuid() for c in self.client.get_active_connections()}:raise ValueError('Disconnect this profile before deleting it.')
                profile.delete_async(None,self.finish(payload,profile.delete_finish));return
            if operation=='export':
                path=Path(payload['file']).expanduser()
                if path.exists() and not payload.get('overwrite'):raise ValueError('The export file already exists.')
                clone=NM.SimpleConnection.new_from_dbus(profile.to_dbus(NM.ConnectionSerializationFlags.NO_SECRETS))
                content=json.dumps(typed_document(clone),indent=2) if path.suffix=='.json' else NM.keyfile_write(clone,NM.KeyfileHandlerFlags.NONE,None,None).to_data()[0]
                path=path.resolve();temporary=None
                try:
                    fd,temporary=tempfile.mkstemp(prefix='.network-export-',dir=path.parent)
                    with os.fdopen(fd,'w') as stream:stream.write(content)
                    if path.exists() and not payload.get('overwrite'):raise ValueError('The export file already exists.')
                    os.replace(temporary,path)
                finally:
                    if temporary and os.path.exists(temporary):os.unlink(temporary)
                self.done(payload);return
            device=self.device(payload) if payload.get('device') else None
            if operation=='activate':self.protect(device,payload,lambda:self.activate(payload,profile,device));return
            if payload.get('test') and not device:raise ValueError('Choose an interface before testing this profile.')
            if payload.get('version',profile.get_version_id())!=profile.get_version_id():raise ValueError('This profile changed externally. Reload it before saving.')
            clone=edit_profile(profile,payload['settings']) if operation=='edit' else from_document(payload['document'])
            if clone.get_uuid()!=profile.get_uuid():raise ValueError('Keep the UUID unchanged when editing; clone to create another profile.')
            def update():
                profile.update2(clone.to_dbus(NM.ConnectionSerializationFlags.ALL),NM.SettingsUpdate2Flags.TO_DISK|NM.SettingsUpdate2Flags.NO_REAPPLY,GLib.Variant('a{sv}',{'version-id':GLib.Variant('t',payload.get('version',profile.get_version_id()))}),None,self.finish(payload,profile.update2_finish,lambda _:self.activate(payload,profile,device) if payload.get('test') else self.done(payload)))
            self.preserve_secrets(profile,clone,payload,lambda:self.protect(device,payload,update) if payload.get('test') and device else update())
            return
        if operation in ('create','join','import'):
            device=self.device(payload) if payload.get('device') else None
            ap=None
            if operation=='join':
                if not isinstance(device,NM.DeviceWifi):raise ValueError('Choose a Wi-Fi interface.')
                target=next((a for a in device.get_access_points() if a.get_path()==payload.get('ap') and a.get_ssid() and bytes(a.get_ssid().get_data()).hex()==payload.get('ssidHex')),None)
                if not target:raise ValueError('This access point disappeared. Search again.')
                saved=next((c for c in device.get_available_connections() if target.connection_valid(c)),None)
                if saved:self.protect(device,payload,lambda:self.activate(payload,saved,device,target.get_path()));return
                payload=dict(payload,name=ssid_text(target.get_ssid()),security=security(target),kind='wifi')
                ap=target.get_path()
            if operation=='import':
                profile=import_profile(payload['file'])
                profile.verify()
                if self.client.get_connection_by_uuid(profile.get_uuid()):raise ValueError('A profile with this UUID already exists. Clone or change its UUID before importing.')
            else:
                if payload.get('kind')=='hotspot' and (not isinstance(device,NM.DeviceWifi) or not device.get_capabilities() & NM.DeviceWifiCapabilities.AP):raise ValueError('This Wi-Fi adapter does not support hotspot mode.')
                profile=create_profile(payload,device.get_iface() if device else None)
            if payload.get('activate') or operation=='join':self.protect(device,payload,lambda:self.activate(payload,profile,device,ap,True))
            else:self.client.add_connection2(profile.to_dbus(NM.ConnectionSerializationFlags.ALL),NM.SettingsAddConnection2Flags.TO_DISK,None,True,None,self.finish(payload,self.client.add_connection2_finish,lambda _:self.done(payload,created=profile.get_uuid())))
            return
        raise ValueError('Unknown network action.')


def main():
    loop=GLib.MainLoop();buffer=b'';controller=None
    def emit(value):
        try:print(json.dumps(value),flush=True)
        except BrokenPipeError:loop.quit()
    def ready(source,result):
        nonlocal controller
        try:controller=Controller(NM.Client.new_finish(result),emit)
        except (GLib.Error,ValueError) as error:emit(dict(event='failure',error=str(error)))
    def stdin(fd,condition):
        nonlocal buffer
        try:chunk=os.read(fd,8192)
        except BlockingIOError:return True
        if not chunk:loop.quit();return False
        buffer+=chunk
        if len(buffer)>4*1024*1024:loop.quit();return False
        while b'\n' in buffer:
            line,buffer=buffer.split(b'\n',1);payload={}
            try:
                payload=json.loads(line)
                if not controller:raise ValueError('NetworkManager is still starting.')
                controller.command(payload)
            except (ValueError,TypeError,KeyError,GLib.Error,OSError,OverflowError) as error:emit(dict(event='result',id=payload.get('id',''),ok=False,error=str(error)))
        return True
    NM.Client.new_async(None,ready)
    os.set_blocking(0,False);GLib.io_add_watch(0,GLib.IO_IN|GLib.IO_HUP,stdin)
    GLibUnix.signal_add(GLib.PRIORITY_DEFAULT,signal.SIGTERM,lambda:(loop.quit(),False)[1])
    loop.run()
    if controller:controller.agent.cancel()
    return 0


if __name__=='__main__':sys.exit(main())
