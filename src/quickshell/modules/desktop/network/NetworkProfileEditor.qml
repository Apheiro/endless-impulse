pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets

ColumnLayout {
    id: root
    required property var entry
    property string section: entry.settings.vpn || entry.settings.wireguard ? "vpn" : "general"
    property bool advanced: false
    property bool catalog: false
    property string query: ""
    readonly property var contextDevice: entry.device ? NetworkControl.devices.find(d => d.id === entry.device) || null : NetworkControl.profileDevice({id: entry.uuid})
    readonly property var sections: [{id: "general", name: Translation.tr("Connection"), icon: "settings_ethernet"}, ...(entry.settings.vpn || entry.settings.wireguard ? [{id: "vpn", name: "VPN", icon: "vpn_key"}] : []), ...(entry.settings.ipv4 ? [{id: "ipv4", name: "IPv4", icon: "lan"}] : []), ...(entry.settings.ipv6 ? [{id: "ipv6", name: "IPv6", icon: "lan"}] : []), {id: "advanced", name: Translation.tr("Advanced"), icon: "tune"}]
    Layout.fillWidth: true
    spacing: 12
    function submit(test) {
        try {
            const payload = {uuid: entry.uuid, version: entry.version, test: test, device: contextDevice?.id || "", interface: contextDevice?.interface || ""};
            if (advanced) { payload.document = JSON.parse(raw.text); NetworkControl.command("advanced", payload); }
            else {
                const data = {};
                for (const [key,value] of Object.entries({name: name.text.trim(), autoconnect: autoConnect.checked, metered: metered.checked})) if (value !== entry.settings[key]) data[key] = value;
                if (entry.settings.ipv4) { const diff = ip4.changes(); if (Object.keys(diff).length) data.ipv4 = diff; }
                if (entry.settings.ipv6) { const diff = ip6.changes(); if (Object.keys(diff).length) data.ipv6 = diff; }
                if (entry.settings.mtu !== undefined) { if (Number(mtu.text) !== entry.settings.mtu) data.mtu = Number(mtu.text); if (mac.text.trim() !== entry.settings.mac) data.mac = mac.text.trim(); }
                if (password.text) data.password = password.text;
                if (vpn.item) Object.assign(data, vpn.item.changes());
                payload.settings = data; NetworkControl.command("edit", payload); password.text = "";
                if (vpn.item) vpn.item.clearSecrets();
            }
        } catch(error) { NetworkControl.failed = true; NetworkControl.message = String(error); }
    }
    Component.onCompleted: { name.text = entry.settings.name; autoConnect.checked = entry.settings.autoconnect; metered.checked = entry.settings.metered; mtu.text = String(entry.settings.mtu ?? 0); mac.text = entry.settings.mac || ""; raw.text = JSON.stringify(entry.document, null, 2); }
    RowLayout {
        Layout.fillWidth: true
        ColumnLayout {
            Layout.fillWidth: true
            StyledText { Layout.fillWidth: true; text: root.entry.settings.name; textFormat: Text.PlainText; elide: Text.ElideRight; font.pixelSize: Appearance.font.pixelSize.larger; font.weight: Font.DemiBold }
            StyledText { Layout.fillWidth: true; text: root.contextDevice ? root.contextDevice.interface : Translation.tr("Saved connection profile"); color: Appearance.colors.colSubtext; font.pixelSize: Appearance.font.pixelSize.smaller }
        }
        RippleButtonWithIcon { materialIcon: "refresh"; mainText: Translation.tr("Reload"); onClicked: NetworkControl.edit({id: root.entry.uuid}) }
        RippleButtonWithIcon { materialIcon: "close"; mainText: ""; onClicked: { NetworkControl.editor = {}; NetworkControl.editingUuid = ""; } }
    }
    Flow {
        Layout.fillWidth: true
        spacing: 6
        Repeater {
            model: root.sections
            delegate: RippleButtonWithIcon { required property var modelData; materialIcon: modelData.icon; mainText: modelData.name; toggled: root.section === modelData.id; onClicked: { root.section = modelData.id; if (root.section !== "advanced") root.advanced = false; } }
        }
    }
    NetworkEditorSection {
        visible: root.section === "general"
        title: Translation.tr("Connection identity & behavior")
        icon: "settings_ethernet"
        StyledText { text: Translation.tr("Profile name"); font.pixelSize: Appearance.font.pixelSize.small }
        MaterialTextField { id: name; Layout.fillWidth: true; wrapMode: TextInput.NoWrap }
        RowLayout { StyledSwitch { id: autoConnect } StyledText { Layout.fillWidth: true; text: Translation.tr("Connect automatically"); wrapMode: Text.WordWrap } }
        RowLayout { StyledSwitch { id: metered } StyledText { Layout.fillWidth: true; text: Translation.tr("Metered connection"); wrapMode: Text.WordWrap } }
        StyledText { visible: root.entry.settings.passwordEditable; text: Translation.tr("New password (leave empty to keep current)"); font.pixelSize: Appearance.font.pixelSize.small }
        MaterialTextField { id: password; visible: root.entry.settings.passwordEditable; Layout.fillWidth: true; wrapMode: TextInput.NoWrap; echoMode: TextInput.Password }
    }
    Loader { id: vpn; Layout.fillWidth: true; active: !!root.entry.settings.vpn || !!root.entry.settings.wireguard; visible: root.section === "vpn"; sourceComponent: NetworkVpnEditor { settings: root.entry.settings } }
    NetworkIpEditor { id: ip4; wireguard: root.entry.settings.kind === "wireguard"; visible: root.section === "ipv4"; settings: root.entry.settings.ipv4 || {} }
    NetworkIpEditor { id: ip6; wireguard: root.entry.settings.kind === "wireguard"; visible: root.section === "ipv6"; settings: root.entry.settings.ipv6 || {}; ipv6: true }
    NetworkEditorSection {
        visible: root.section === "advanced"
        title: Translation.tr("Link & advanced settings")
        icon: "tune"
        ColumnLayout {
            Layout.fillWidth: true
            visible: root.entry.settings.mtu !== undefined
            StyledText { text: Translation.tr("MTU in bytes (0 = automatic)"); font.pixelSize: Appearance.font.pixelSize.small }
            MaterialTextField { id: mtu; Layout.fillWidth: true; wrapMode: TextInput.NoWrap; validator: IntValidator { bottom: 0; top: 65535 } }
            StyledText { text: Translation.tr("Cloned MAC address or policy"); font.pixelSize: Appearance.font.pixelSize.small }
            MaterialTextField { id: mac; Layout.fillWidth: true; wrapMode: TextInput.NoWrap; placeholderText: "preserve / permanent / random / stable" }
        }
        RippleButtonWithIcon { materialIcon: root.advanced ? "expand_less" : "data_object"; mainText: Translation.tr("All NetworkManager properties"); onClicked: root.advanced = !root.advanced }
        StyledText { Layout.fillWidth: true; visible: root.advanced; text: Translation.tr("Raw mode saves this document instead of the guided form. Existing secrets are hidden; keep the UUID unchanged."); wrapMode: Text.WordWrap; color: Appearance.colors.colSubtext; font.pixelSize: Appearance.font.pixelSize.smaller }
        MaterialTextArea { id: raw; visible: root.advanced; Layout.fillWidth: true; Layout.preferredHeight: 360; wrapMode: TextEdit.Wrap; font.family: Appearance.font.family.monospace; font.pixelSize: Appearance.font.pixelSize.smaller }
        RippleButtonWithIcon { visible: root.advanced; materialIcon: "help_outline"; mainText: Translation.tr("Property reference"); onClicked: { root.catalog = !root.catalog; if (!NetworkControl.schema.length) NetworkControl.command("schema"); } }
    ColumnLayout {
        Layout.fillWidth:true;visible:root.advanced&&root.catalog
        MaterialTextField{Layout.fillWidth:true;wrapMode:TextInput.NoWrap;placeholderText:Translation.tr("Find a setting or property…");onTextChanged:root.query=text.toLowerCase()}
        Repeater {
            model:NetworkControl.schema
            delegate:ColumnLayout {
                id:setting
                required property var modelData
                property bool expanded:false
                readonly property var properties:modelData.properties.filter(p=>(modelData.name+" "+p.name+" "+p.description).toLowerCase().includes(root.query))
                visible:properties.length>0
                Layout.fillWidth:true
                RippleButtonWithIcon{materialIcon:setting.expanded?"expand_less":"expand_more";mainText:setting.modelData.name;onClicked:setting.expanded=!setting.expanded}
                Repeater {
                    model:setting.expanded||root.query.length>0?setting.properties:[]
                    delegate:StyledText { required property var modelData;Layout.fillWidth:true;textFormat:Text.PlainText;text:modelData.name+" ["+modelData.type+"]"+(modelData.secret?" · "+Translation.tr("Secret"):"")+"\n"+modelData.description;wrapMode:Text.WordWrap;font.pixelSize:Appearance.font.pixelSize.smaller;color:Appearance.colors.colSubtext }
                }
            }
        }
    }
    }
    Flow {
        Layout.fillWidth: true
        spacing: 6
        RippleButtonWithIcon { materialIcon: "save"; mainText: Translation.tr("Save profile"); enabled: !NetworkControl.pending(root.entry.uuid); onClicked: root.submit(false) }
        RippleButtonWithIcon { materialIcon: "science"; mainText: Translation.tr("Apply & test (45 s)"); enabled: !!root.contextDevice && !NetworkControl.pending(root.entry.uuid); onClicked: root.submit(true) }
    }
    StyledText { Layout.fillWidth: true; text: Translation.tr("Save updates the profile without disconnecting. Apply & test reconnects; confirm Keep to retain the change."); wrapMode: Text.WordWrap; color: Appearance.colors.colSubtext; font.pixelSize: Appearance.font.pixelSize.smaller }
}
