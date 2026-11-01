pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets
import qs.modules.desktop.network

ColumnLayout {
    id: root
    objectName: "quick-content-network"
    spacing: 10
    property double now: Date.now()/1000
    Timer { interval: 1000; repeat: true; running: !!NetworkControl.state.checkpoint?.path; onTriggered: root.now = Date.now()/1000 }
    Loader {
        Layout.fillWidth: true
        active: !!NetworkControl.state.checkpoint?.path
        visible: active
        sourceComponent: ColumnLayout {
            StyledText { Layout.fillWidth: true; text: Translation.tr("Keep this connection?") + " · " + Math.max(0, Math.ceil((NetworkControl.state.checkpoint.expires || 0) - root.now)) + " s"; wrapMode: Text.WordWrap; color: Appearance.colors.colPrimary }
            RowLayout {
                RippleButtonWithIcon { materialIcon: "undo"; mainText: Translation.tr("Revert"); onClicked: NetworkControl.command("rollback") }
                RippleButtonWithIcon { objectName: "quick-network-keep"; materialIcon: "check"; mainText: Translation.tr("Keep"); onClicked: NetworkControl.command("keep") }
            }
        }
    }
    RowLayout {
        Layout.fillWidth: true
        ColumnLayout {
            Layout.fillWidth: true
            StyledText { text: Translation.tr("Current connection"); color: Appearance.colors.colSubtext; font.pixelSize: Appearance.font.pixelSize.smaller }
            StyledText { Layout.fillWidth: true; text: NetworkControl.state.primary || Translation.tr("Not connected"); textFormat: Text.PlainText; elide: Text.ElideRight }
        }
        StyledText { text: "Wi-Fi"; font.pixelSize: Appearance.font.pixelSize.small }
        StyledSwitch { checked: NetworkControl.state.wifiEnabled ?? false; enabled: NetworkControl.wifiDevices.length > 0 && NetworkControl.state.wifiHardware; onToggled: NetworkControl.wifi(checked) }
    }
    RowLayout {
        Layout.fillWidth: true
        StyledText { Layout.fillWidth: true; text: NetworkControl.scanning ? Translation.tr("Searching for networks…") : Translation.tr("Available networks"); color: Appearance.colors.colSubtext; font.pixelSize: Appearance.font.pixelSize.smaller }
        RippleButtonWithIcon { materialIcon: "refresh"; mainText: ""; enabled: NetworkControl.state.wifiEnabled && !NetworkControl.scanning; onClicked: { for (const device of NetworkControl.wifiDevices) NetworkControl.scan(device); } }
    }
    Loader { Layout.fillWidth: true; active: NetworkControl.scanning; visible: active; sourceComponent: StyledIndeterminateProgressBar {} }
    StyledText { Layout.fillWidth: true; visible: NetworkControl.message.length > 0; text: NetworkControl.message; wrapMode: Text.WordWrap; color: Appearance.colors.colSubtext }
    Loader { Layout.fillWidth: true; active: !!NetworkControl.prompt.id; visible: active; sourceComponent: NetworkSecretPrompt {} }
    Loader {
        Layout.fillWidth: true
        active: !!NetworkControl.creator.kind
        visible: active
        sourceComponent: ColumnLayout {
            StyledText { Layout.fillWidth: true; text: NetworkControl.creator.ssid || ""; textFormat: Text.PlainText; elide: Text.ElideRight; font.pixelSize: Appearance.font.pixelSize.small }
            MaterialTextField { id: password; Layout.fillWidth: true; wrapMode: TextInput.NoWrap; echoMode: TextInput.Password; placeholderText: Translation.tr("Network password") }
            RippleButtonWithIcon {
                materialIcon: "link"
                mainText: Translation.tr("Connect")
                onClicked: { const payload = Object.assign({}, NetworkControl.creator, {password: password.text}); NetworkControl.command("join", payload); password.text = ""; NetworkControl.creator = {}; }
            }
            RippleButtonWithIcon { materialIcon: "close"; mainText: Translation.tr("Cancel"); onClicked: NetworkControl.creator = {} }
        }
    }
    StyledFlickable {
        Layout.fillWidth: true
        Layout.fillHeight: true
        implicitHeight: Math.min(310, networks.implicitHeight)
        contentHeight: networks.implicitHeight
        clip: true
        ColumnLayout {
            id: networks
            width: parent.width
            spacing: 4
            Repeater {
                model: NetworkControl.networks
                delegate: RippleButton {
                    id: network
                    required property var modelData
                    Layout.fillWidth: true
                    implicitHeight: 44
                    toggled: modelData.active
                    colBackgroundToggled: Appearance.colors.colSecondaryContainer
                    colBackgroundToggledHover: Appearance.colors.colSecondaryContainerHover
                    enabled: !modelData.active && !NetworkControl.pending(modelData.device)
                    opacity: modelData.active || enabled ? 1 : 0.4
                    onClicked: {
                        if (modelData.security === "enterprise" && !modelData.profiles.length) { NetworkControl.failed = false; NetworkControl.message = Translation.tr("Set up enterprise networks from Network settings in the right sidebar."); }
                        else { NetworkControl.chooseNetwork(modelData); if (["open", "owe"].includes(modelData.security) && NetworkControl.creator.kind) { NetworkControl.command("join", NetworkControl.creator); NetworkControl.creator = {}; } }
                    }
                    contentItem: RowLayout {
                        MaterialSymbol { text: network.modelData.active ? "check" : network.modelData.security === "open" ? "wifi" : "wifi_lock"; iconSize: 20; color: network.toggled ? Appearance.colors.colOnSecondaryContainer : Appearance.colors.colOnLayer0 }
                        StyledText { Layout.fillWidth: true; text: network.modelData.ssid; textFormat: Text.PlainText; elide: Text.ElideRight; color: network.toggled ? Appearance.colors.colOnSecondaryContainer : Appearance.colors.colOnLayer0; font.pixelSize: Appearance.font.pixelSize.small }
                        StyledText { text: network.modelData.strength + "%"; color: network.toggled ? Appearance.colors.colOnSecondaryContainer : Appearance.colors.colSubtext; font.pixelSize: Appearance.font.pixelSize.smaller }
                    }
                }
            }
            StyledText { visible: !NetworkControl.networks.length; Layout.fillWidth: true; text: !NetworkControl.wifiDevices.length ? Translation.tr("No Wi-Fi adapter") : !NetworkControl.state.wifiEnabled ? Translation.tr("Wi-Fi is off") : NetworkControl.scanning ? Translation.tr("Searching…") : Translation.tr("No networks found"); wrapMode: Text.WordWrap; color: Appearance.colors.colSubtext; font.pixelSize: Appearance.font.pixelSize.small }
        }
    }
}
