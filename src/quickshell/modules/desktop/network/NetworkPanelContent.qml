pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.settings
import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import QtQuick.Dialogs
import Quickshell
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets

ColumnLayout {
    id:root
    property bool embedded:false
    signal dismissed()
    property string query:""
    property string deleteUuid:""
    property string exportUuid:""
    property string confirmOffline:""
    property double now:Date.now()/1000
    Connections{target:NetworkControl;function onEditorChanged(){if(NetworkControl.editor.uuid)scroll.contentY=0;}function onCreatorChanged(){if(NetworkControl.creator.kind)scroll.contentY=0;}}
    property ListModel deviceRows:ListModel{dynamicRoles:true}
    property ListModel networkRows:ListModel{dynamicRoles:true}
    property ListModel profileRows:ListModel{dynamicRoles:true}
    function sync(model,rows){
        const ids=rows.map(row=>row.id);
        for(let i=model.count-1;i>=0;i--)if(!ids.includes(model.get(i).identity))model.remove(i);
        rows.forEach((row,index)=>{
            let previous=-1;
            for(let i=index;i<model.count;i++)if(model.get(i).identity===row.id){previous=i;break;}
            if(previous<0)model.insert(index,{identity:row.id,entry:row});
            else{if(previous!==index)model.move(previous,index,1);model.setProperty(index,"entry",row);}
        });
    }
    function updateRows(){
        sync(deviceRows,NetworkControl.devices.filter(d=>(d.interface+" "+d.kind).toLowerCase().includes(query)));
        sync(networkRows,NetworkControl.networks.filter(n=>n.ssid.toLowerCase().includes(query)));
        sync(profileRows,NetworkControl.profiles.filter(p=>(p.name+" "+p.kind).toLowerCase().includes(query)));
    }
    Component.onCompleted:updateRows()
    onQueryChanged:updateRows()
    Connections{target:NetworkControl;function onStateChanged(){root.updateRows();}}
    spacing:12
    FileDialog {
        id:importFile;title:Translation.tr("Import network profile");options:FileDialog.DontUseNativeDialog
        nameFilters:["Network profiles (*.nmconnection *.conf *.ovpn *.pcf *.json)","All files (*)"]
        onAccepted:NetworkControl.command("import",{file:decodeURIComponent(selectedFile.toString().replace(/^file:\/\//,""))})
    }
    FileDialog {
        id:exportFile;title:Translation.tr("Export without passwords");options:FileDialog.DontUseNativeDialog;fileMode:FileDialog.SaveFile
        nameFilters:["NetworkManager (*.nmconnection)","Typed settings (*.json)"]
        onAccepted:NetworkControl.command("export",{uuid:root.exportUuid,file:decodeURIComponent(selectedFile.toString().replace(/^file:\/\//,"")),overwrite:true})
    }
    Timer{interval:1000;repeat:true;running:!!NetworkControl.state.checkpoint?.path;onTriggered:root.now=Date.now()/1000}
    RowLayout {
        Layout.fillWidth:true
        visible: !root.embedded
        MaterialSymbol{text:"settings_ethernet";iconSize:30;color:Appearance.colors.colPrimary}
        ColumnLayout {
            Layout.fillWidth:true;spacing:2
            StyledText{text:Translation.tr("Network");font.pixelSize:Appearance.font.pixelSize.title;font.weight:Font.DemiBold}
            StyledText{Layout.fillWidth:true;text:NetworkControl.state.primary||Translation.tr("Not connected");textFormat:Text.PlainText;elide:Text.ElideRight;color:Appearance.colors.colSubtext;font.pixelSize:Appearance.font.pixelSize.smaller}
        }
        RippleButtonWithIcon { materialIcon:"power_settings_new";mainText:NetworkControl.state.networking?Translation.tr("Disable networking"):Translation.tr("Enable networking");onClicked:{if(NetworkControl.state.networking)root.confirmOffline="yes";else NetworkControl.command("networking",{enabled:true});} }
        RippleButtonWithIcon{materialIcon:"refresh";mainText:"";onClicked:NetworkControl.refresh()}
        RippleButtonWithIcon{materialIcon:"close";mainText:"";onClicked:root.dismissed()}
    }
    RowLayout {
        visible:root.embedded
        Layout.fillWidth:true
        StyledText{Layout.fillWidth:true;text:NetworkControl.state.primary||Translation.tr("Not connected");textFormat:Text.PlainText;elide:Text.ElideRight;color:Appearance.colors.colSubtext}
        RippleButtonWithIcon{materialIcon:"power_settings_new";mainText:NetworkControl.state.networking?Translation.tr("Disable networking"):Translation.tr("Enable networking");onClicked:{if(NetworkControl.state.networking)root.confirmOffline="yes";else NetworkControl.command("networking",{enabled:true});}}
    }
    RowLayout{visible:root.confirmOffline.length>0;Layout.fillWidth:true;StyledText{Layout.fillWidth:true;text:Translation.tr("Disconnect all network interfaces?");wrapMode:Text.WordWrap}RippleButtonWithIcon{materialIcon:"close";mainText:Translation.tr("Cancel");onClicked:root.confirmOffline=""}RippleButtonWithIcon{materialIcon:"power_settings_new";mainText:Translation.tr("Disable");onClicked:{NetworkControl.command("networking",{enabled:false});root.confirmOffline="";}}}
    RowLayout {
        Layout.fillWidth:true
        Repeater {
            model:[{id:"devices",name:Translation.tr("Interfaces"),icon:"lan"},{id:"wifi",name:"Wi-Fi",icon:"wifi"},{id:"profiles",name:Translation.tr("Saved profiles"),icon:"bookmark"}]
            delegate:RippleButtonWithIcon{required property var modelData;materialIcon:modelData.icon;mainText:modelData.name;toggled:NetworkControl.page===modelData.id;onClicked:{NetworkControl.editor={};NetworkControl.creator={};NetworkControl.page=modelData.id;}}
        }
        Item{Layout.fillWidth:true}
        StyledText{text:"Wi-Fi";color:Appearance.colors.colSubtext}
        StyledSwitch{enabled:NetworkControl.loaded&&NetworkControl.wifiDevices.length>0&&NetworkControl.state.wifiHardware;checked:NetworkControl.state.wifiEnabled??false;onToggled:NetworkControl.wifi(checked)}
    }
    RowLayout {
        Layout.fillWidth:true
        StyledText{Layout.fillWidth:true;text:Translation.tr("Connectivity: ")+(NetworkControl.state.connectivity||"unknown");color:Appearance.colors.colSubtext;font.pixelSize:Appearance.font.pixelSize.smaller}
        RippleButtonWithIcon{materialIcon:"public";mainText:Translation.tr("Check Internet");onClicked:NetworkControl.command("connectivity")}
        RippleButtonWithIcon{visible:NetworkControl.state.connectivity==="portal";materialIcon:"login";mainText:Translation.tr("Sign in");onClicked:Qt.openUrlExternally("https://nmcheck.gnome.org/")}
    }
    Rectangle {
        Layout.fillWidth:true;visible:!!NetworkControl.state.checkpoint?.path
        implicitHeight:checkpointRow.implicitHeight+18;color:Appearance.colors.colLayer0;border.width:1;border.color:Appearance.colors.colPrimary;radius:Appearance.rounding.normal
        RowLayout {
            id:checkpointRow;anchors{fill:parent;margins:9}
            StyledText{Layout.fillWidth:true;text:Translation.tr("Keep this connection? Reverting in ")+Math.max(0,Math.ceil((NetworkControl.state.checkpoint.expires||0)-root.now))+" s";wrapMode:Text.WordWrap;color:Appearance.colors.colPrimary}
            RippleButtonWithIcon{materialIcon:"undo";mainText:Translation.tr("Revert");onClicked:NetworkControl.command("rollback")}
            RippleButtonWithIcon{materialIcon:"check";mainText:Translation.tr("Keep");onClicked:NetworkControl.command("keep")}
        }
    }
    StyledText{Layout.fillWidth:true;visible:NetworkControl.message.length>0;text:NetworkControl.message;textFormat:Text.PlainText;wrapMode:Text.WordWrap;color:NetworkControl.failed?Appearance.m3colors.m3error:Appearance.colors.colSubtext}
    StyledText{Layout.fillWidth:true;visible:!NetworkControl.loaded||!NetworkControl.state.available;text:!NetworkControl.loaded?Translation.tr("Connecting to NetworkManager…"):Translation.tr("NetworkManager is not running");color:Appearance.colors.colSubtext}
    RippleButtonWithIcon{visible:!NetworkControl.loaded;materialIcon:"refresh";mainText:Translation.tr("Retry service");onClicked:NetworkControl.retry()}
    Loader{Layout.fillWidth:true;active:!!NetworkControl.prompt.id;visible:active;sourceComponent:NetworkSecretPrompt{}}
    Loader {
        Layout.fillWidth:true
        objectName:"networkScanIndicator"
        active:NetworkControl.scanning
        visible:active
        sourceComponent:ColumnLayout {
            spacing:4
            StyledText{text:Translation.tr("Searching for Wi-Fi networks…");color:Appearance.colors.colPrimary;font.pixelSize:Appearance.font.pixelSize.smaller}
            StyledIndeterminateProgressBar{Layout.fillWidth:true}
        }
    }
    MaterialTextField{Layout.fillWidth:true;wrapMode:TextInput.NoWrap;visible:!NetworkControl.editor.uuid&&!NetworkControl.creator.kind;placeholderText:Translation.tr("Filter interfaces, networks or profiles…");onTextChanged:root.query=text.toLowerCase()}
    StyledFlickable {
        id:scroll
        Layout.fillWidth:true;Layout.fillHeight:true;clip:true
        contentHeight:body.implicitHeight+12
        ColumnLayout {
            id:body;width:scroll.width;spacing:10
            Loader{Layout.fillWidth:true;active:!!NetworkControl.creator.kind;visible:active;sourceComponent:NetworkCreateProfile{initial:NetworkControl.creator}}
            Loader{Layout.fillWidth:true;active:!!NetworkControl.editor.uuid;visible:active;sourceComponent:NetworkProfileEditor{entry:NetworkControl.editor}}
            ColumnLayout {
                visible:!NetworkControl.editor.uuid&&!NetworkControl.creator.kind&&NetworkControl.page==="devices"
                Layout.fillWidth:true
                Repeater{model:root.deviceRows;delegate:NetworkDeviceCard{required property var entry;device:entry}}
            }
            ColumnLayout {
                visible:!NetworkControl.editor.uuid&&!NetworkControl.creator.kind&&NetworkControl.page==="wifi"
                Layout.fillWidth:true
                Flow {
                    Layout.fillWidth:true;spacing:6
                    Repeater{model:NetworkControl.wifiDevices;delegate:RippleButtonWithIcon{required property var modelData;materialIcon:"search";mainText:(NetworkControl.pending(modelData.id)?Translation.tr("Scanning "):Translation.tr("Scan "))+modelData.interface;enabled:NetworkControl.state.wifiEnabled&&!NetworkControl.pending(modelData.id);onClicked:NetworkControl.scan(modelData)}}
                    RippleButtonWithIcon{materialIcon:"wifi_find";mainText:Translation.tr("Hidden network");enabled:NetworkControl.wifiDevices.length>0;onClicked:{NetworkControl.create("wifi",NetworkControl.wifiDevices[0]);NetworkControl.creator=Object.assign({},NetworkControl.creator,{hidden:true});}}
                    RippleButtonWithIcon{materialIcon:"wifi_tethering";mainText:Translation.tr("Hotspot");enabled:NetworkControl.wifiDevices.some(device=>device.hotspot);onClicked:NetworkControl.create("hotspot",NetworkControl.wifiDevices.find(device=>device.hotspot))}
                }
                Repeater {
                    model:root.networkRows
                    delegate:SettingsCard {
                        id:network
                        required property var entry
                        readonly property var modelData:entry
                        Layout.fillWidth:true;implicitHeight:networkRow.implicitHeight+20
                        emphasized: modelData.active
                        RowLayout {
                            id:networkRow;anchors{fill:parent;margins:10}
                            MaterialSymbol{text:network.modelData.security==="open"?"wifi":"wifi_lock";iconSize:24;color:Appearance.colors.colPrimary}
                            ColumnLayout {
                                Layout.fillWidth:true;spacing:2
                                StyledText{Layout.fillWidth:true;text:network.modelData.ssid;textFormat:Text.PlainText;elide:Text.ElideRight}
                                StyledText{Layout.fillWidth:true;text:network.modelData.security+" · "+network.modelData.strength+"% · "+network.modelData.frequency+" MHz · "+network.modelData.interface;elide:Text.ElideRight;color:Appearance.colors.colSubtext;font.pixelSize:Appearance.font.pixelSize.smaller}
                            }
                            RippleButtonWithIcon{materialIcon:network.modelData.active?"check":"link";mainText:network.modelData.active?Translation.tr("Connected"):Translation.tr("Connect");enabled:!network.modelData.active&&NetworkControl.agentReady&&!NetworkControl.pending(network.modelData.device);onClicked:NetworkControl.chooseNetwork(network.modelData)}
                        }
                    }
                }
                StyledText{visible:!NetworkControl.wifiDevices.length;Layout.fillWidth:true;text:Translation.tr("No Wi-Fi adapter found");wrapMode:Text.WordWrap;color:Appearance.colors.colSubtext}
            }
            ColumnLayout {
                visible:!NetworkControl.editor.uuid&&!NetworkControl.creator.kind&&NetworkControl.page==="profiles"
                Layout.fillWidth:true
                Flow {
                    Layout.fillWidth:true;spacing:6
                    RippleButtonWithIcon{materialIcon:"add";mainText:Translation.tr("New profile");onClicked:NetworkControl.create("ethernet")}
                    RippleButtonWithIcon{materialIcon:"vpn_key";mainText:Translation.tr("New VPN");onClicked:NetworkControl.create("vpn")}
                    RippleButtonWithIcon{materialIcon:"file_open";mainText:Translation.tr("Import");onClicked:importFile.open()}
                }
                Repeater {
                    model:root.profileRows
                    delegate:ColumnLayout {
                        id:profile
                        required property var entry
                        readonly property var modelData:entry
                        Layout.fillWidth:true
                        RowLayout {
                            Layout.fillWidth:true
                            ColumnLayout {
                                Layout.fillWidth:true
                                StyledText{Layout.fillWidth:true;text:profile.modelData.name;textFormat:Text.PlainText;elide:Text.ElideRight}
                                StyledText{Layout.fillWidth:true;text:profile.modelData.kind+(profile.modelData.active?" · "+Translation.tr("Active"):"");elide:Text.ElideRight;color:Appearance.colors.colSubtext;font.pixelSize:Appearance.font.pixelSize.smaller}
                            }
                            RippleButtonWithIcon{materialIcon:"link";mainText:"";enabled:!profile.modelData.active&&NetworkControl.agentReady;onClicked:NetworkControl.activate(profile.modelData,NetworkControl.profileDevice(profile.modelData))}
                            RippleButtonWithIcon{materialIcon:"edit";mainText:"";onClicked:NetworkControl.edit(profile.modelData)}
                            RippleButtonWithIcon{materialIcon:"more_horiz";mainText:"";onClicked:profile.expanded=!profile.expanded}
                        }
                        property bool expanded:false
                        Flow {
                            Layout.fillWidth:true;visible:profile.expanded;spacing:6
                            RippleButtonWithIcon{materialIcon:"content_copy";mainText:Translation.tr("Clone");onClicked:NetworkControl.command("clone",{uuid:profile.modelData.id})}
                            RippleButtonWithIcon{materialIcon:"file_save";mainText:Translation.tr("Export");onClicked:{root.exportUuid=profile.modelData.id;exportFile.open();}}
                            RippleButtonWithIcon{materialIcon:"delete";mainText:Translation.tr("Forget");enabled:!profile.modelData.active;onClicked:root.deleteUuid=profile.modelData.id}
                        }
                        RowLayout{visible:root.deleteUuid===profile.modelData.id;StyledText{Layout.fillWidth:true;text:Translation.tr("Delete this saved connection?");wrapMode:Text.WordWrap}RippleButtonWithIcon{materialIcon:"close";mainText:Translation.tr("Cancel");onClicked:root.deleteUuid=""}RippleButtonWithIcon{materialIcon:"delete";mainText:Translation.tr("Delete");onClicked:{NetworkControl.command("delete",{uuid:profile.modelData.id});root.deleteUuid="";}}}
                    }
                }
            }
        }
    }
}
