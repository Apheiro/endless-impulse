pragma Singleton
pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland
import qs

Singleton {
    id:root
    property bool opened:false
    property string screenName:""
    property bool loaded:false
    property bool agentReady:false
    property bool failed:false
    property string message:""
    property string page:"devices"
    property var state:({devices:[],networks:[],profiles:[],checkpoint:{},available:false,wifiEnabled:false,wifiHardware:false})
    property var prompt:({})
    property var queue:[]
    property var operations:({})
    property int sequence:0
    property bool enabled:true
    property var editor:({})
    property var creator:({})
    property var schema:[]
    property var vpnServices:[]
    property string editingUuid:""
    property string editingDevice:""
    readonly property var devices:state.devices||[]
    readonly property var profiles:state.profiles||[]
    readonly property var accessPoints:state.networks||[]
    readonly property var wifiDevices:devices.filter(device=>device.kind==="wifi")
    readonly property var networks: {
        const groups={};
        for(const network of accessPoints){
            const key=network.device+":"+network.ssidHex+":"+network.security;
            if(!groups[key] || network.active || (!groups[key].active && network.strength>groups[key].strength)) groups[key]=network;
        }
        return Object.values(groups).sort((a,b)=>Number(b.active)-Number(a.active)||b.strength-a.strength||a.ssid.localeCompare(b.ssid));
    }
    signal operationCompleted(string id, string action, bool success)
    readonly property bool scanning:(state.scanning||[]).length>0||Object.values(operations).some(item=>item.action==="scan")
    readonly property bool busy:Object.keys(operations).length>0
    function open(name,section){screenName=name||Hyprland.focusedMonitor?.name||Quickshell.screens[0]?.name||"";opened=true;if(section)page=section;QuickPanelState.activate("network");GlobalStates.sidebarRightOpen=false;command("panel",{open:true});}
    function close(){QuickPanelState.deactivate("network");if(prompt.id)respond(false,{});creator={};editor={};editingUuid="";opened=false;command("panel",{open:false});}
    function pending(identity){return (state.scanning||[]).includes(identity)||Object.values(operations).some(item=>item.uuid===identity||item.device===identity);}
    function command(action,payload){
        const request=Object.assign({id:String(++sequence),action:action},payload||{});
        operations=Object.assign({},operations,{[request.id]:{action:action,device:request.device||"",uuid:request.uuid||""}});
        queue=[...queue,request];drain();return request.id;
    }
    function drain(){if(!loaded||!worker.running)return;const requests=queue;queue=[];for(const request of requests)worker.write(JSON.stringify(request)+"\n");}
    function respond(accept,values){command("respond",{prompt:prompt.id,accept:accept,values:values});}
    function refresh(){command("refresh");}
    function scan(device){command("scan",{device:device.id,interface:device.interface});}
    function wifi(enabled){command("wifi",{enabled:enabled});}
    function edit(profile,device){if(device!==undefined)editingDevice=device?.id||"";else if(editingUuid!==profile.id)editingDevice="";editingUuid=profile.id;creator={};editor={};command("details",{uuid:profile.id,device:editingDevice});}
    function create(kind,device){creator={kind:kind||"wifi",device:device?.id||"",interface:device?.interface||""};editor={};}
    function chooseNetwork(network){
        if(network.active)return;
        const device=devices.find(device=>device.id===network.device);
        if(network.profiles.length){command("join",{device:network.device,interface:network.interface,ap:network.id,ssidHex:network.ssidHex});return;}
        creator=Object.assign({},network,{kind:"wifi",ssid:network.ssid,name:network.ssid,device:device?.id||"",ap:network.id});editor={};
    }
    function activate(profile,device){command("activate",{uuid:profile.id,device:device?.id||"",interface:device?.interface||""});}
    function profileDevice(profile){return devices.find(device=>device.profiles.includes(profile.id))||null;}
    function retry(){enabled=false;restartTimer.restart();}
    Timer{id:restartTimer;interval:250;onTriggered:root.enabled=true}
    Connections{target:GlobalStates;function onScreenLockedChanged(){if(GlobalStates.screenLocked)root.close();}}
    Process {
        id:worker
        running:root.enabled
        stdinEnabled:true
        command:["python3",Quickshell.shellPath("scripts/network/control.py")]
        stdout:SplitParser{onRead:line=>{
            try{
                const data=JSON.parse(line);
                if(data.event==="state"){
                    root.state=data.state;root.loaded=true;root.drain();
                }else if(data.event==="agent"){root.agentReady=data.ok;if(!data.ok){root.failed=true;root.message=data.error;}}
                else if(data.event==="prompt"){
                    root.prompt=data.prompt;
                    if(root.prompt.id && (!root.opened||GlobalStates.screenLocked))root.respond(false,{});
                }else if(data.event==="scan-error"){root.failed=true;root.message=data.error;}
                else if(data.event==="failure"){root.failed=true;root.message=data.error;}
                else if(data.event==="result"){
                    const operation=root.operations[data.id];const next=Object.assign({},root.operations);delete next[data.id];root.operations=next;
                    if(!data.ok){root.failed=true;root.message=data.error;}
                    else if(operation?.action!=="refresh" && operation?.action!=="panel"){root.failed=false;root.message="";}
                    if(data.document && operation?.uuid===root.editingUuid)root.editor={uuid:operation.uuid,device:operation.device,document:data.document,settings:data.settings,version:data.version};
                    if(data.schema)root.schema=data.schema;
                    if(data.vpnServices)root.vpnServices=data.vpnServices;
                    if(data.created)root.edit({id:data.created});
                    if(data.ok && ["edit","advanced"].includes(operation?.action) && operation.uuid===root.editingUuid)root.edit({id:operation.uuid});
                    if(operation)root.operationCompleted(data.id,operation.action,data.ok);
                }
            }catch(error){root.failed=true;root.message="Could not read network state: "+error;}
        }}
        stderr:StdioCollector{id:errors}
        onExited:{root.loaded=false;root.agentReady=false;root.operations={};root.queue=[];root.prompt={};if(root.enabled){root.failed=true;root.message=errors.text||"Network service stopped. Retry to reconnect.";}}
    }
    IpcHandler {
        target:"network"
        function open(){root.open();}
        function close(){root.close();}
        function toggle(){if(root.opened)root.close();else root.open();}
        function scan(){for(const device of root.wifiDevices)if(root.state.wifiEnabled&&!root.pending(device.id))root.scan(device);}
        function status():string{return JSON.stringify({loaded:root.loaded,wifiEnabled:root.state.wifiEnabled,adapters:root.wifiDevices.length,operations:Object.values(root.operations).map(op=>op.action),scanning:root.scanning,devices:root.state.scanning||[],error:root.failed?root.message:""});}
    }
}
