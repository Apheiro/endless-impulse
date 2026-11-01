pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets

ColumnLayout {
    id: root
    objectName: "network-vpn-editor"
    required property var settings
    readonly property var vpn: settings.vpn || {}
    readonly property var wg: settings.wireguard || null
    readonly property var vpnData: vpn.data || {}
    readonly property bool openvpn: vpn.service === "org.freedesktop.NetworkManager.openvpn"
    readonly property var modes: ["tls", "password", "password-tls", "static-key", ...(!["tls", "password", "password-tls", "static-key"].includes(vpnData["connection-type"] || "tls") ? [vpnData["connection-type"]] : [])]
    readonly property string mode: modes[auth.currentIndex] || "tls"
    readonly property var fields: [
        {key: "remote", label: Translation.tr("VPN server / gateway"), file: false},
        {key: "port", label: Translation.tr("Server port (empty = default)"), file: false},
        {key: "username", label: Translation.tr("Username"), file: false, modes: ["password", "password-tls"]},
        {key: "ca", label: Translation.tr("CA certificate"), file: true, modes: ["tls", "password", "password-tls"]},
        {key: "cert", label: Translation.tr("Client certificate"), file: true, modes: ["tls", "password-tls"]},
        {key: "key", label: Translation.tr("Private key file"), file: true, modes: ["tls", "password-tls"]},
        {key: "verify-x509-name", label: Translation.tr("Expected server certificate name (optional)"), file: false},
        {key: "static-key", label: Translation.tr("Static key file"), file: true, modes: ["static-key"]},
        {key: "local-ip", label: Translation.tr("Local tunnel address"), file: false, modes: ["static-key"]},
        {key: "remote-ip", label: Translation.tr("Remote tunnel address"), file: false, modes: ["static-key"]},
        {key: "cipher", label: Translation.tr("Cipher (empty = negotiated / default)"), file: false},
        {key: "auth", label: Translation.tr("Authentication digest (optional)"), file: false},
        {key: "tls-crypt", label: Translation.tr("TLS crypt key (optional)"), file: true},
        {key: "ta", label: Translation.tr("TLS authentication key (optional)"), file: true}
    ]
    property ListModel peers: ListModel { dynamicRoles: true }
    property ListModel properties: ListModel { dynamicRoles: true }
    property ListModel extraSecrets: ListModel { dynamicRoles: true }
    readonly property var coreFields: fields.filter(f => ["remote", "port", "username", "ca", "cert", "key", "static-key", "local-ip", "remote-ip"].includes(f.key))
    readonly property var optionalFields: fields.filter(f => !coreFields.some(c => c.key === f.key))
    property bool showOptions: false
    property bool showExtra: false
    Layout.fillWidth: true
    spacing: 12
    function changes() {
        if (wg) {
            const result = {};
            if (Number(listen.text) !== wg.listenPort) result.listenPort = Number(listen.text);
            if (peerRoutes.checked !== wg.peerRoutes) result.peerRoutes = peerRoutes.checked;
            if (privateKey.text) result.privateKey = privateKey.text.trim();
            const values = Array.from({length: peers.count}, (_, i) => { const p = peers.get(i); const row = {publicKey: p.publicKey.trim(), endpoint: p.endpoint.trim(), allowedIps: p.allowedIps.split(",").map(s => s.trim()).filter(Boolean), keepalive: Number(p.keepalive)}; if (p.presharedKey) row.presharedKey = p.presharedKey.trim(); return row; });
            if (JSON.stringify(values) !== JSON.stringify(wg.peers)) result.peers = values;
            return Object.keys(result).length ? {wireguard: result} : {};
        }
        const changed = {}, secrets = {};
        if (openvpn) {
            for (const repeater of [fieldRepeater, optionalRepeater]) for (let i = 0; i < repeater.count; i++) { const field = repeater.itemAt(i); if (field.text.trim() !== (vpnData[field.modelData.key] || "")) changed[field.modelData.key] = field.text.trim(); }
            if (mode !== (vpnData["connection-type"] || "tls")) changed["connection-type"] = mode;
            if ((protocol.currentIndex === 1) !== (vpnData["proto-tcp"] === "yes")) changed["proto-tcp"] = protocol.currentIndex === 1 ? "yes" : "no";
            if (password.text) secrets.password = password.text;
            if (keyPassword.text) secrets["cert-pass"] = keyPassword.text;
        }
        const current = {};
        for (let i = 0; i < properties.count; i++) { const p = properties.get(i); if (p.key.trim()) current[p.key.trim()] = p.value; }
        const editable = {};
        for (const [key, value] of Object.entries(vpnData)) if (!openvpn || !fields.some(f => f.key === key) && !["connection-type", "proto-tcp"].includes(key)) editable[key] = value;
        for (const key of new Set([...Object.keys(editable), ...Object.keys(current)])) if ((current[key] || "") !== (editable[key] || "")) changed[key] = current[key] || "";
        for (let i = 0; i < extraSecrets.count; i++) { const row = extraSecrets.get(i); if (row.key.trim() && row.value) secrets[row.key.trim()] = row.value; }
        return Object.keys(changed).length || Object.keys(secrets).length ? {vpn: {data: changed, secrets: secrets}} : {};
    }
    function clearSecrets() { privateKey.text = ""; password.text = ""; keyPassword.text = ""; for (let i = 0; i < peers.count; i++) peers.setProperty(i, "presharedKey", ""); for (let i = 0; i < extraSecrets.count; i++) extraSecrets.setProperty(i, "value", ""); }
    Component.onCompleted: {
        if (wg) { listen.text = String(wg.listenPort); peerRoutes.checked = wg.peerRoutes; for (const p of wg.peers) peers.append({publicKey: p.publicKey, endpoint: p.endpoint, allowedIps: p.allowedIps.join(", "), keepalive: String(p.keepalive), presharedKey: ""}); }
        else {
            auth.currentIndex = Math.max(0, modes.indexOf(vpnData["connection-type"] || "tls")); protocol.currentIndex = vpnData["proto-tcp"] === "yes" ? 1 : 0;
            for (const [key, value] of Object.entries(vpnData)) if (!openvpn || !fields.some(f => f.key === key) && !["connection-type", "proto-tcp"].includes(key)) properties.append({key: key, value: value});
        }
    }
    NetworkEditorSection {
        visible: !root.wg
        title: root.openvpn ? "OpenVPN" : root.vpn.service || "VPN"
        icon: "vpn_key"
        description: root.vpn.available ? Translation.tr("The NetworkManager VPN plugin is available on this machine.") : Translation.tr("This VPN needs its NetworkManager plugin on the host before it can connect.")
        ColumnLayout {
            Layout.fillWidth: true
            visible: root.openvpn
            StyledText { text: Translation.tr("Authentication"); font.pixelSize: Appearance.font.pixelSize.small }
            StyledComboBox { id: auth; Layout.fillWidth: true; model: root.modes.map(id => ({name: ({tls: Translation.tr("Certificates (TLS)"), password: Translation.tr("Username & password"), "password-tls": Translation.tr("Password + certificates"), "static-key": Translation.tr("Static key")})[id] || id})); textRole: "name" }
            StyledText { text: Translation.tr("Transport"); font.pixelSize: Appearance.font.pixelSize.small }
            StyledComboBox { id: protocol; model: ["UDP", "TCP"] }
            Repeater {
                id: fieldRepeater
                model: root.coreFields
                delegate: NetworkLabeledField {
                    required property var modelData
                    label: modelData.label
                    filePath: modelData.file
                    visible: !modelData.modes || modelData.modes.includes(root.mode)
                    Component.onCompleted: text = root.vpnData[modelData.key] || ""
                }
            }
            NetworkLabeledField { id: password; visible: ["password", "password-tls"].includes(root.mode); label: Translation.tr("New password (empty keeps current)"); secret: true }
            NetworkLabeledField { id: keyPassword; visible: ["tls", "password-tls"].includes(root.mode); label: Translation.tr("New private key password (optional)"); secret: true }
        }
    }
    NetworkEditorSection {
        visible: root.openvpn
        title: Translation.tr("Optional security settings")
        icon: "security"
        RippleButtonWithIcon { materialIcon: root.showOptions ? "expand_less" : "expand_more"; mainText: Translation.tr("Certificate checks & encryption"); onClicked: root.showOptions = !root.showOptions }
        ColumnLayout {
            visible: root.showOptions
            Layout.fillWidth: true
            Repeater {
                id: optionalRepeater
                model: root.optionalFields
                delegate: NetworkLabeledField {
                    required property var modelData
                    label: modelData.label
                    filePath: modelData.file
                    visible: !modelData.modes || modelData.modes.includes(root.mode)
                    Component.onCompleted: text = root.vpnData[modelData.key] || ""
                }
            }
        }
    }
    NetworkEditorSection {
        visible: !!root.wg
        title: "WireGuard"
        icon: "vpn_key"
        NetworkLabeledField { id: privateKey; label: Translation.tr("New private key (empty keeps current)"); secret: true }
        NetworkLabeledField { id: listen; label: Translation.tr("Listen port (0 = automatic)"); validator: IntValidator { bottom: 0; top: 65535 } }
        RowLayout { StyledSwitch { id: peerRoutes } StyledText { Layout.fillWidth: true; text: Translation.tr("Create routes from peers’ allowed networks"); wrapMode: Text.WordWrap } }
        Repeater {
            model: root.peers
            delegate: ColumnLayout {
                id: peer
                required property int index
                required property string publicKey
                required property string endpoint
                required property string allowedIps
                required property string keepalive
                required property string presharedKey
                Layout.fillWidth: true
                RowLayout { Layout.fillWidth: true; StyledText { Layout.fillWidth: true; text: Translation.tr("Peer ") + (peer.index + 1); color: Appearance.colors.colPrimary } RippleButtonWithIcon { materialIcon: "delete"; mainText: ""; onClicked: root.peers.remove(peer.index) } }
                NetworkLabeledField { label: Translation.tr("Public key"); text: peer.publicKey; onTextChanged: if (text !== peer.publicKey) root.peers.setProperty(peer.index, "publicKey", text) }
                NetworkLabeledField { label: Translation.tr("Endpoint (host:port)"); text: peer.endpoint; onTextChanged: if (text !== peer.endpoint) root.peers.setProperty(peer.index, "endpoint", text) }
                NetworkLabeledField { label: Translation.tr("Allowed networks, separated by commas"); text: peer.allowedIps; onTextChanged: if (text !== peer.allowedIps) root.peers.setProperty(peer.index, "allowedIps", text) }
                NetworkLabeledField { label: Translation.tr("Keepalive in seconds (0 = off)"); text: peer.keepalive; validator: IntValidator { bottom: 0; top: 65535 } onTextChanged: if (text !== peer.keepalive) root.peers.setProperty(peer.index, "keepalive", text) }
                NetworkLabeledField { label: Translation.tr("New pre-shared key (optional)"); text: peer.presharedKey; secret: true; onTextChanged: if (text !== peer.presharedKey) root.peers.setProperty(peer.index, "presharedKey", text) }
            }
        }
        RippleButtonWithIcon { materialIcon: "add"; mainText: Translation.tr("Add peer"); onClicked: root.peers.append({publicKey: "", endpoint: "", allowedIps: "", keepalive: "0", presharedKey: ""}) }
    }
    NetworkEditorSection {
        visible: !root.wg
        title: Translation.tr("Plugin properties")
        icon: "tune"
        description: Translation.tr("Additional plugin options are edited as named fields. Import a VPN configuration to populate them automatically.")
        RippleButtonWithIcon { materialIcon: root.showExtra ? "expand_less" : "expand_more"; mainText: Translation.tr("Additional properties") + " (" + root.properties.count + ")"; onClicked: root.showExtra = !root.showExtra }
        ColumnLayout {
            visible: root.showExtra || !root.openvpn
            Layout.fillWidth: true
            Repeater {
                model: root.properties
                delegate: RowLayout {
                    id: option
                    required property int index
                    required property string key
                    required property string value
                    Layout.fillWidth: true
                    MaterialTextField { Layout.fillWidth: true; text: option.key; wrapMode: TextInput.NoWrap; placeholderText: Translation.tr("Property"); onTextEdited: root.properties.setProperty(option.index, "key", text) }
                    MaterialTextField { Layout.fillWidth: true; text: option.value; wrapMode: TextInput.NoWrap; placeholderText: Translation.tr("Value"); onTextEdited: root.properties.setProperty(option.index, "value", text) }
                    RippleButtonWithIcon { materialIcon: "delete"; mainText: ""; onClicked: root.properties.remove(option.index) }
                }
            }
            RippleButtonWithIcon { materialIcon: "add"; mainText: Translation.tr("Add property"); onClicked: root.properties.append({key: "", value: ""}) }
            Repeater {
                model: root.extraSecrets
                delegate: RowLayout {
                    id: credential
                    required property int index
                    required property string key
                    required property string value
                    Layout.fillWidth: true
                    MaterialTextField { Layout.fillWidth: true; text: credential.key; wrapMode: TextInput.NoWrap; placeholderText: Translation.tr("Secret name"); onTextEdited: root.extraSecrets.setProperty(credential.index, "key", text) }
                    MaterialTextField { Layout.fillWidth: true; text: credential.value; wrapMode: TextInput.NoWrap; echoMode: TextInput.Password; placeholderText: Translation.tr("New secret"); onTextEdited: root.extraSecrets.setProperty(credential.index, "value", text) }
                    RippleButtonWithIcon { materialIcon: "delete"; mainText: ""; onClicked: root.extraSecrets.remove(credential.index) }
                }
            }
            RippleButtonWithIcon { materialIcon: "key"; mainText: Translation.tr("Add credential"); onClicked: root.extraSecrets.append({key: "", value: ""}) }
        }
    }
}
