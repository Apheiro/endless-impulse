pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets

ColumnLayout {
    id:root
    required property var initial
    property bool advanced:false
    property string submission:""
    readonly property string kind:types[type.currentIndex]||"wifi"
    readonly property var types:["wifi","ethernet","hotspot","wireguard","vpn","vlan","bridge","bond","pppoe"]
    readonly property var securities:["wpa-psk","sae","enterprise","owe","open","wep"]
    readonly property var deviceOptions:NetworkControl.devices.filter(d=>["wifi","hotspot"].includes(root.kind)?d.kind==="wifi":root.kind==="ethernet"||root.kind==="pppoe"?d.kind==="ethernet":false)
    readonly property var vpnChoices: ["org.freedesktop.NetworkManager.openvpn", ...NetworkControl.vpnServices.filter(s=>s!=="org.freedesktop.NetworkManager.openvpn"), "custom"].map(service=>({service:service,name:service==="custom"?Translation.tr("Other VPN plugin…"):({openvpn:"OpenVPN",openconnect:"OpenConnect",strongswan:"IKEv2 / strongSwan",vpnc:"Cisco IPSec",l2tp:"L2TP",pptp:"PPTP",fortisslvpn:"Fortinet SSL VPN"})[service.split(".").pop()]||service.split(".").pop()}))
    onKindChanged:if(kind==="vpn"&&!NetworkControl.vpnServices.length)NetworkControl.command("vpn-plugins")
    property string certificateTarget:"ca"
    FileDialog {
        id:certificate
        options:FileDialog.DontUseNativeDialog
        nameFilters:["Certificates and keys (*.pem *.crt *.cer *.der *.p12 *.pfx *.key)","All files (*)"]
        onAccepted:{const field=({ca:ca,clientCert:clientCert,privateKey:privateKey})[root.certificateTarget];field.text=decodeURIComponent(selectedFile.toString().replace(/^file:\/\//,""));}
    }
    Layout.fillWidth:true;spacing:10
    function submit(activate){
        const device=deviceOptions[adapter.currentIndex];
        const payload={kind:root.kind,name:name.text.trim()||ssid.text,ssid:ssid.text,security:securities[security.currentIndex],hidden:hidden.checked,password:root.kind==="pppoe"?pppPassword.text:password.text,remember:remember.checked,autoconnect:autoConnect.checked,device:device?.id||"",interface:device?.interface||"",interfaceName:iface.text.trim(),activate:activate,identity:root.kind==="pppoe"?pppUser.text:identity.text,eap:eap.currentText,phase2:phase2.currentText,ca:ca.text,systemCa:systemCa.checked,domain:domain.text,clientCert:clientCert.text,privateKey:privateKey.text,keyPassword:keyPassword.text,service:(vpnChoices[service.currentIndex]?.service==="custom"?customService.text:vpnChoices[service.currentIndex]?.service)||"org.freedesktop.NetworkManager.openvpn",parent:parentLink.text,vlan:Number(vlan.text)};
        if(initial.ap){payload.ap=initial.ap;payload.ssidHex=initial.ssidHex;}
        submission=NetworkControl.command(initial.ap&&activate?"join":"create",payload);
        password.text="";keyPassword.text="";pppPassword.text="";
    }
    Connections { target:NetworkControl;function onOperationCompleted(id,action,success){if(id===root.submission){root.submission="";if(success)NetworkControl.creator={};}} }
    Component.onCompleted:{type.currentIndex=Math.max(0,types.indexOf(initial.kind));ssid.text=initial.ssid||"";name.text=initial.name||"";security.currentIndex=Math.max(0,securities.indexOf(initial.security||"wpa-psk"));hidden.checked=!!initial.hidden;adapter.currentIndex=Math.max(0,deviceOptions.findIndex(d=>d.id===initial.device));}
    RowLayout {
        Layout.fillWidth:true
        StyledText{Layout.fillWidth:true;text:Translation.tr("New connection");font.pixelSize:Appearance.font.pixelSize.larger}
        RippleButtonWithIcon{materialIcon:"close";mainText:"";onClicked:NetworkControl.creator={}}
    }
    StyledComboBox{id:type;model:root.types.map(id=>({name:({wifi:"Wi-Fi",ethernet:"Ethernet",hotspot:Translation.tr("Wi-Fi hotspot"),wireguard:"WireGuard",vpn:"VPN",vlan:"VLAN",bridge:Translation.tr("Bridge"),bond:Translation.tr("Bond"),pppoe:"PPPoE"})[id],id:id}));textRole:"name";enabled:!root.initial.ap}
    MaterialTextField{id:name;Layout.fillWidth:true;wrapMode:TextInput.NoWrap;placeholderText:Translation.tr("Profile name")}
    StyledComboBox{id:adapter;visible:root.deviceOptions.length>0;model:root.deviceOptions.map(d=>({name:d.interface,id:d.id}));textRole:"name"}
    MaterialTextField{id:iface;visible:!["wifi","hotspot","ethernet"].includes(root.kind);Layout.fillWidth:true;wrapMode:TextInput.NoWrap;placeholderText:Translation.tr("Virtual interface name (optional)")}
    ColumnLayout {
        visible:["wifi","hotspot"].includes(root.kind)
        Layout.fillWidth:true
        MaterialTextField{id:ssid;Layout.fillWidth:true;readOnly:!!root.initial.ap;wrapMode:TextInput.NoWrap;placeholderText:"SSID";maximumLength:32}
        StyledComboBox{id:security;model:root.securities.map(id=>({name:({"wpa-psk":"WPA / WPA2 Personal",sae:"WPA3 Personal",enterprise:"WPA Enterprise / 802.1X",owe:"Enhanced Open (OWE)",open:Translation.tr("Open network"),wep:"WEP (legacy)"})[id],id:id}));textRole:"name"}
        RowLayout{StyledSwitch{id:hidden}StyledText{text:Translation.tr("Hidden network")}}
        MaterialTextField{id:password;visible:!["open","owe"].includes(root.securities[security.currentIndex]);Layout.fillWidth:true;wrapMode:TextInput.NoWrap;echoMode:TextInput.Password;placeholderText:Translation.tr("Password")}
        RowLayout{StyledSwitch{id:remember;checked:true}StyledText{Layout.fillWidth:true;text:Translation.tr("Save password with NetworkManager");wrapMode:Text.WordWrap}}
        ColumnLayout {
            visible:root.securities[security.currentIndex]==="enterprise"
            Layout.fillWidth:true
            MaterialTextField{id:identity;Layout.fillWidth:true;wrapMode:TextInput.NoWrap;placeholderText:Translation.tr("Identity / username")}
            StyledComboBox{id:eap;model:["peap","ttls","tls"]}
            StyledComboBox{id:phase2;visible:eap.currentText!=="tls";model:["mschapv2","pap","chap","mschap","gtc"]}
            RowLayout{StyledSwitch{id:systemCa;checked:true}StyledText{text:Translation.tr("Use system CA certificates")}}
            RowLayout { Layout.fillWidth:true;MaterialTextField{id:ca;Layout.fillWidth:true;wrapMode:TextInput.NoWrap;placeholderText:Translation.tr("CA certificate path (optional)")} RippleButtonWithIcon{materialIcon:"folder_open";mainText:"";onClicked:{root.certificateTarget="ca";certificate.open();}} }
            MaterialTextField{id:domain;Layout.fillWidth:true;wrapMode:TextInput.NoWrap;placeholderText:Translation.tr("Authentication server domain")}
            RowLayout { Layout.fillWidth:true;visible:eap.currentText==="tls";MaterialTextField{id:clientCert;Layout.fillWidth:true;wrapMode:TextInput.NoWrap;placeholderText:Translation.tr("Client certificate path")} RippleButtonWithIcon{materialIcon:"folder_open";mainText:"";onClicked:{root.certificateTarget="clientCert";certificate.open();}} }
            RowLayout { Layout.fillWidth:true;visible:eap.currentText==="tls";MaterialTextField{id:privateKey;Layout.fillWidth:true;wrapMode:TextInput.NoWrap;placeholderText:Translation.tr("Private key path")} RippleButtonWithIcon{materialIcon:"folder_open";mainText:"";onClicked:{root.certificateTarget="privateKey";certificate.open();}} }
            MaterialTextField{id:keyPassword;visible:eap.currentText==="tls";Layout.fillWidth:true;wrapMode:TextInput.NoWrap;echoMode:TextInput.Password;placeholderText:Translation.tr("Private key password")}
        }
    }
    ColumnLayout {
        visible:root.kind==="pppoe";Layout.fillWidth:true
        MaterialTextField{id:pppUser;Layout.fillWidth:true;wrapMode:TextInput.NoWrap;placeholderText:Translation.tr("PPPoE username")}
        MaterialTextField{id:pppPassword;Layout.fillWidth:true;wrapMode:TextInput.NoWrap;echoMode:TextInput.Password;placeholderText:Translation.tr("PPPoE password")}
    }
    StyledText{visible:root.kind==="vpn";text:Translation.tr("VPN provider / protocol");font.pixelSize:Appearance.font.pixelSize.small}
    StyledComboBox{id:service;visible:root.kind==="vpn";Layout.fillWidth:true;model:root.vpnChoices;textRole:"name"}
    MaterialTextField{id:customService;visible:root.kind==="vpn"&&root.vpnChoices[service.currentIndex]?.service==="custom";Layout.fillWidth:true;wrapMode:TextInput.NoWrap;placeholderText:"org.freedesktop.NetworkManager.plugin"}
    RowLayout {
        visible:root.kind==="vlan";Layout.fillWidth:true
        MaterialTextField{id:parentLink;Layout.fillWidth:true;wrapMode:TextInput.NoWrap;placeholderText:Translation.tr("Parent interface or UUID")}
        MaterialTextField{id:vlan;text:"1";validator:IntValidator{bottom:0;top:4094}Layout.preferredWidth:100;wrapMode:TextInput.NoWrap;placeholderText:"VLAN ID"}
    }
    RowLayout{StyledSwitch{id:autoConnect}StyledText{text:Translation.tr("Connect automatically")}}
    StyledText { visible:["vpn","wireguard","bridge","bond","vlan","pppoe"].includes(root.kind);Layout.fillWidth:true;text:Translation.tr("Save the base profile, then configure its additional properties in the editor. You can also import a complete profile.");wrapMode:Text.WordWrap;color:Appearance.colors.colSubtext }
    RowLayout {
        RippleButtonWithIcon{materialIcon:"save";mainText:Translation.tr("Save profile");enabled:root.submission.length===0;onClicked:root.submit(false)}
        RippleButtonWithIcon{materialIcon:"link";mainText:Translation.tr("Connect & test");visible:["wifi","hotspot","ethernet"].includes(root.kind);enabled:NetworkControl.agentReady&&root.submission.length===0;onClicked:root.submit(true)}
    }
}
