pragma Singleton
pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import qs.services.network

// Compatibility facade for existing bars, launchers and optional panel families.
Singleton {
    id:root
    readonly property bool wifiEnabled:NetworkControl.state.wifiEnabled??false
    readonly property bool ethernet:NetworkControl.devices.some(device=>device.kind==="ethernet"&&device.state==="activated")
    readonly property bool wifi:NetworkControl.devices.some(device=>device.kind==="wifi"&&device.state==="activated")
    readonly property bool wifiScanning:NetworkControl.scanning
    readonly property bool wifiConnecting:Object.values(NetworkControl.operations).some(item=>["join","activate","create"].includes(item.action))
    property var wifiConnectTarget:null
    property list<WifiAccessPoint> wifiNetworks:[]
    readonly property var active:wifiNetworks.find(network=>network.active)??null
    readonly property var friendlyWifiNetworks:[...wifiNetworks].sort((a,b)=>Number(b.active)-Number(a.active)||b.strength-a.strength)
    readonly property string networkName:NetworkControl.state.primary||""
    readonly property int networkStrength:active?.strength??0
    readonly property string wifiStatus:!wifiEnabled?"disabled":wifiConnecting?"connecting":wifi?(NetworkControl.state.connectivity==="full"?"connected":"limited"):"disconnected"
    readonly property string materialSymbol:ethernet?"lan":!wifiEnabled?"signal_wifi_off":wifi?networkStrength>70?"signal_wifi_4_bar":networkStrength>40?"network_wifi_3_bar":"network_wifi_2_bar":"wifi_find"
    function update(){NetworkControl.refresh();}
    function enableWifi(enabled=true){NetworkControl.wifi(enabled);}
    function toggleWifi(){if(NetworkControl.wifiDevices.length)enableWifi(!wifiEnabled);else NetworkControl.open();}
    function rescanWifi(){for(const device of NetworkControl.wifiDevices)if(wifiEnabled)NetworkControl.scan(device);}
    function connectToWifiNetwork(network){const target=NetworkControl.accessPoints.find(item=>item.id===network.lastIpcObject.id);if(target){NetworkControl.open(undefined,"wifi");NetworkControl.chooseNetwork(target);}}
    function disconnectWifiNetwork(){const device=NetworkControl.devices.find(item=>item.kind==="wifi"&&item.active);if(device)NetworkControl.command("disconnect",{device:device.id,interface:device.interface});}
    function changePassword(network,password,username=""){connectToWifiNetwork(network);}
    function openPublicWifiPortal(){Qt.openUrlExternally("https://nmcheck.gnome.org/");}
    function sync(){
        const rows=NetworkControl.networks;
        const old=wifiNetworks;
        for(let i=old.length-1;i>=0;i--)if(!rows.some(row=>row.id===old[i].lastIpcObject.id)){const object=old[i];old.splice(i,1);object.destroy();}
        for(const row of rows){const object=old.find(item=>item.lastIpcObject.id===row.id);if(object)object.lastIpcObject=row;else old.push(ap.createObject(root,{lastIpcObject:row}));}
    }
    Component.onCompleted:sync()
    Connections{target:NetworkControl;function onAccessPointsChanged(){root.sync();}}
    Component{id:ap;WifiAccessPoint{}}
}
