pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import Quickshell
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets
import qs.modules.desktop.bluetooth

ColumnLayout {
    id: root
    objectName: "quick-content-bluetooth"
    property bool discovery: false
    spacing: 10
    RowLayout {
        Layout.fillWidth: true
        StyledText { Layout.fillWidth: true; text: BluetoothManager.adapter?.name || Translation.tr("No Bluetooth adapter"); textFormat: Text.PlainText; elide: Text.ElideRight; font.pixelSize: Appearance.font.pixelSize.small }
        StyledSwitch { checked: BluetoothManager.adapter?.enabled ?? false; enabled: !!BluetoothManager.adapter; onToggled: BluetoothManager.setPowered(checked) }
    }
    Loader { Layout.fillWidth: true; active: !!BluetoothManager.prompt.id; visible: active; sourceComponent: BluetoothPairingPrompt {} }
    StyledText { Layout.fillWidth: true; visible: BluetoothManager.message.length > 0; text: BluetoothManager.message; wrapMode: Text.WordWrap; color: Appearance.colors.colSubtext }
    StyledText { text: Translation.tr("Connected devices"); color: Appearance.colors.colSubtext; font.pixelSize: Appearance.font.pixelSize.smaller }
    StyledFlickable {
        Layout.fillWidth: true
        Layout.fillHeight: true
        implicitHeight: Math.min(300, devices.implicitHeight)
        contentHeight: devices.implicitHeight
        clip: true
        ColumnLayout {
            id: devices
            width: parent.width
            spacing: 4
            Repeater {
                model: ScriptModel { values: BluetoothManager.devices.filter(d => d.connected || (root.discovery && !d.blocked)) }
                delegate: RowLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    StyledText { Layout.fillWidth: true; text: modelData.name; textFormat: Text.PlainText; elide: Text.ElideRight; font.pixelSize: Appearance.font.pixelSize.small }
                    StyledText { visible: modelData.batteryAvailable; text: Math.round(modelData.battery * 100) + "%"; color: Appearance.colors.colSubtext; font.pixelSize: Appearance.font.pixelSize.smaller }
                    RippleButtonWithIcon {
                        materialIcon: modelData.connected ? "link_off" : "link"
                        mainText: modelData.connected ? Translation.tr("Disconnect") : Translation.tr("Connect")
                        enabled: BluetoothManager.agentReady && !BluetoothManager.pending(modelData.dbusPath)
                        onClicked: BluetoothManager.command(modelData.connected ? "disconnect" : modelData.paired ? "connect" : "pair", modelData.dbusPath)
                    }
                }
            }
            StyledText { visible: !BluetoothManager.devices.some(d => d.connected) && !root.discovery; text: Translation.tr("No connected devices"); color: Appearance.colors.colSubtext; font.pixelSize: Appearance.font.pixelSize.small }
        }
    }
    RippleButtonWithIcon {
        Layout.fillWidth: true
        materialIcon: BluetoothManager.adapter?.discovering ? "stop" : "search"
        mainText: BluetoothManager.adapter?.discovering ? Translation.tr("Stop searching") : Translation.tr("Find devices")
        enabled: (BluetoothManager.adapter?.enabled ?? false) && (!BluetoothManager.adapter.discovering || !!BluetoothManager.scanOwner)
        onClicked: { root.discovery = true; BluetoothManager.scan(); }
    }
    Loader { Layout.fillWidth: true; active: BluetoothManager.adapter?.discovering ?? false; visible: active; sourceComponent: StyledIndeterminateProgressBar {} }
}
