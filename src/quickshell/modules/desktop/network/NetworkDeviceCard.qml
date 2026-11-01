pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.settings
import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets

SettingsCard {
    id:root
    required property var device
    property bool expanded:false
    property string selectedUuid:""
    readonly property var selectedProfile:device.active?NetworkControl.profiles.find(p=>p.id===device.active)||null:available.find(p=>p.id===selectedUuid)||available[profile.currentIndex]||null
    readonly property var available:NetworkControl.profiles.filter(profile=>device.profiles.includes(profile.id))
    Layout.fillWidth:true
    implicitHeight:body.implicitHeight+28
    emphasized: !!device.active
    ColumnLayout {
        id:body
        anchors{left:parent.left;right:parent.right;top:parent.top;margins:14}
        spacing:8
        RowLayout {
            Layout.fillWidth:true
            MaterialSymbol{text:root.device.kind==="wifi"?"wifi":root.device.kind==="ethernet"?"lan":"hub";iconSize:28;color:Appearance.colors.colPrimary}
            ColumnLayout {
                Layout.fillWidth:true
                StyledText{Layout.fillWidth:true;text:root.device.interface;textFormat:Text.PlainText;font.weight:Font.Medium;elide:Text.ElideRight}
                StyledText{Layout.fillWidth:true;text:root.device.state+(root.device.kind==="ethernet"?" · "+(root.device.carrier?String(root.device.speed)+" Mb/s":Translation.tr("No cable")):"");elide:Text.ElideRight;color:Appearance.colors.colSubtext;font.pixelSize:Appearance.font.pixelSize.smaller}
            }
            RippleButtonWithIcon { objectName:"configure-network-interface";materialIcon:"settings";mainText:Translation.tr("Configure");enabled:!!root.selectedProfile;onClicked:NetworkControl.edit(root.selectedProfile,root.device) }
            RippleButtonWithIcon { visible:!!root.device.active;materialIcon:"link_off";mainText:Translation.tr("Disconnect");enabled:!NetworkControl.pending(root.device.id);onClicked:NetworkControl.command("disconnect",{device:root.device.id,interface:root.device.interface}) }
            RippleButtonWithIcon { materialIcon:root.expanded?"expand_less":"expand_more";mainText:"";onClicked:root.expanded=!root.expanded }
        }
        StyledText{Layout.fillWidth:true;visible:!!root.device.active;text:Translation.tr("Active profile: ")+(root.selectedProfile?.name||root.device.active);textFormat:Text.PlainText;elide:Text.ElideRight;color:Appearance.colors.colSubtext;font.pixelSize:Appearance.font.pixelSize.smaller}
        RowLayout {
            Layout.fillWidth:true
            visible:!root.device.active && root.available.length>0
            StyledComboBox{id:profile;Layout.fillWidth:true;model:root.available;textRole:"name";onActivated:index=>root.selectedUuid=root.available[index].id}
            RippleButtonWithIcon{materialIcon:"link";mainText:Translation.tr("Connect");enabled:profile.currentIndex>=0&&NetworkControl.agentReady;onClicked:NetworkControl.activate(root.selectedProfile,root.device)}
        }
        ColumnLayout {
            Layout.fillWidth:true;visible:root.expanded
            StyledText{Layout.fillWidth:true;text:root.device.hw;textFormat:Text.PlainText;font.family:Appearance.font.family.monospace;font.pixelSize:Appearance.font.pixelSize.smaller;color:Appearance.colors.colSubtext}
            Repeater {
                model:["ip4","ip6"]
                delegate:ColumnLayout {
                    id:family
                    required property string modelData
                    readonly property var ip:root.device[modelData]||{}
                    Layout.fillWidth:true
                    visible:(ip.addresses||[]).length>0
                    StyledText{text:family.modelData==="ip4"?"IPv4":"IPv6";color:Appearance.colors.colPrimary;font.weight:Font.Medium}
                    Repeater {
                        model:[{label:Translation.tr("Addresses"),value:(family.ip.addresses||[]).join(", ")},{label:Translation.tr("Gateway"),value:family.ip.gateway||""},{label:"DNS",value:(family.ip.dns||[]).join(", ")},{label:Translation.tr("Domains"),value:(family.ip.domains||[]).join(", ")},{label:Translation.tr("Routes"),value:(family.ip.routes||[]).map(r=>r.destination+(r.gateway?" → "+r.gateway:"")+" · "+r.metric).join("\n")}]
                        delegate:RowLayout {
                            required property var modelData
                            Layout.fillWidth:true;visible:!!modelData.value
                            StyledText{Layout.preferredWidth:100;text:modelData.label;color:Appearance.colors.colSubtext;font.pixelSize:Appearance.font.pixelSize.smaller}
                            StyledText{Layout.fillWidth:true;text:modelData.value;textFormat:Text.PlainText;wrapMode:Text.WrapAnywhere;font.family:Appearance.font.family.monospace;font.pixelSize:Appearance.font.pixelSize.smaller}
                        }
                    }
                }
            }
            StyledText { Layout.fillWidth:true;visible:root.device.reason!=="none";text:Translation.tr("State reason: ")+root.device.reason;textFormat:Text.PlainText;wrapMode:Text.WordWrap;color:Appearance.colors.colSubtext }
            RippleButtonWithIcon{materialIcon:"add";mainText:Translation.tr("New profile");onClicked:NetworkControl.create(root.device.kind==="wifi"?"wifi":"ethernet",root.device)}
        }
    }
}
