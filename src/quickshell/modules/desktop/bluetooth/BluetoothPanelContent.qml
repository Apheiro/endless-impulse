pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Bluetooth
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets

ColumnLayout {
    id: root
    property bool embedded: false
    signal dismissed
    property string query: ""
    readonly property var filtered: BluetoothManager.devices.filter(device => (device.name + " "
                                                                              + device.address).toLowerCase(
                                        ).includes(query.toLowerCase()))
    spacing: 12
    RowLayout {
        Layout.fillWidth: true
        visible: !root.embedded
        MaterialSymbol {
            text: "bluetooth"
            iconSize: 32
            color: Appearance.colors.colPrimary
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            StyledText {
                text: Translation.tr("Bluetooth")
                font.pixelSize: Appearance.font.pixelSize.title
                font.weight: Font.DemiBold
            }
            StyledText {
                Layout.fillWidth: true
                text: BluetoothManager.adapter?.name || Translation.tr("No Bluetooth adapter found")
                elide: Text.ElideRight
                color: Appearance.colors.colSubtext
                font.pixelSize: Appearance.font.pixelSize.smaller
            }
        }
        StyledSwitch {
            enabled: !!BluetoothManager.adapter
            checked: BluetoothManager.adapter?.enabled ?? false
            onToggled: BluetoothManager.setPowered(checked)
        }
        RippleButtonWithIcon {
            materialIcon: "close"
            mainText: ""
            onClicked: root.dismissed()
        }
    }
    RowLayout {
        visible: root.embedded
        Layout.fillWidth: true
        StyledText { Layout.fillWidth: true; text: BluetoothManager.adapter?.name || Translation.tr("No Bluetooth adapter"); elide: Text.ElideRight; color: Appearance.colors.colSubtext }
        StyledSwitch { enabled: !!BluetoothManager.adapter; checked: BluetoothManager.adapter?.enabled ?? false; onToggled: BluetoothManager.setPowered(checked) }
    }
    StyledComboBox {
        visible: BluetoothManager.adapters.length > 1
        model: BluetoothManager.adapters.map(item => ({
            name: item.name + " · " + item.adapterId,
            path: item.dbusPath
        }))
        textRole: "name"
        currentIndex: model.findIndex(item => item.path === BluetoothManager.adapter?.dbusPath)
        onActivated: index => BluetoothManager.changeAdapter(model[index].path)
    }
    Flow {
        Layout.fillWidth: true
        spacing: 8
        RippleButtonWithIcon {
            materialIcon: BluetoothManager.adapter?.discovering ? "stop" : "search"
            mainText: BluetoothManager.adapter?.discovering ? Translation.tr("Searching…") : Translation.tr(
                                                                  "Search devices")
            enabled: (BluetoothManager.adapter?.enabled ?? false) && (!BluetoothManager.adapter.discovering ||
                                                                      !!BluetoothManager.scanOwner)
            onClicked: BluetoothManager.scan()
        }
        RippleButtonWithIcon {
            materialIcon: BluetoothManager.receiving ? "visibility" : "visibility_off"
            mainText: BluetoothManager.receiving ? Translation.tr("Visible for 3 minutes") : Translation.tr(
                                                       "Allow incoming pairing")
            toggled: BluetoothManager.receiving
            enabled: (BluetoothManager.adapter?.enabled ?? false) && BluetoothManager.agentReady
            onClicked: BluetoothManager.receive()
        }
        RippleButtonWithIcon {
            materialIcon: "refresh"
            mainText: Translation.tr("Retry service")
            visible: !BluetoothManager.agentReady
            onClicked: BluetoothManager.retry()
        }
    }
    StyledText {
        Layout.fillWidth: true
        visible: BluetoothManager.adapter?.state === BluetoothAdapterState.Blocked
        text: Translation.tr("Bluetooth is blocked by the system or a hardware switch.")
        wrapMode: Text.WordWrap
        color: Appearance.m3colors.m3error
    }
    StyledText {
        Layout.fillWidth: true
        visible: BluetoothManager.message.length > 0
        text: BluetoothManager.message
        wrapMode: Text.WordWrap
        color: BluetoothManager.failed ? Appearance.m3colors.m3error : Appearance.colors.colSubtext
    }
    Loader {
        Layout.fillWidth: true
        active: !!BluetoothManager.prompt.id
        visible: active
        sourceComponent: BluetoothPairingPrompt {}
    }
    MaterialTextField {
        Layout.fillWidth: true
        enabled: BluetoothManager.adapter?.enabled ?? false
        placeholderText: Translation.tr("Search name or address…")
        onTextChanged: root.query = text
    }
    StyledIndeterminateProgressBar {
        Layout.fillWidth: true
        visible: BluetoothManager.adapter?.discovering ?? false
    }
    StyledFlickable {
        id: scroll
        Layout.fillWidth: true
        Layout.fillHeight: true
        clip: true
        contentHeight: body.implicitHeight + 12
        ColumnLayout {
            id: body
            width: scroll.width
            spacing: 10
            Repeater {
                model: [
                    {
                        id: "connected",
                        title: Translation.tr("Connected")
                    },
                    {
                        id: "saved",
                        title: Translation.tr("Saved devices")
                    },
                    {
                        id: "available",
                        title: Translation.tr("Nearby devices")
                    }
                ]
                delegate: ColumnLayout {
                    id: group
                    required property var modelData
                    readonly property var devices: root.filtered.filter(device => modelData.id === "connected"
                                                                                  ? device.connected :
                                                                                    modelData.id === "saved"
                                                                                    ? device.paired &&
                                                                                      !device.connected :
                                                                                      !device.paired &&
                                                                                      !device.connected).sort((
                                                                                                                  a, b) => a.name.localeCompare(
                                                                                                                               b.name))
                    visible: devices.length > 0
                    Layout.fillWidth: true
                    StyledText {
                        text: group.modelData.title + " · " + group.devices.length
                        color: Appearance.colors.colSubtext
                        font.pixelSize: Appearance.font.pixelSize.small
                    }
                    Repeater {
                        model: ScriptModel {
                            values: group.devices
                        }
                        delegate: BluetoothDeviceCard {
                            required property var modelData
                            device: modelData
                        }
                    }
                }
            }
            StyledText {
                Layout.fillWidth: true
                Layout.topMargin: 20
                visible: root.filtered.length === 0
                text: !BluetoothManager.adapter ? Translation.tr("No Bluetooth adapter found") :
                                                  !BluetoothManager.adapter.enabled ? Translation.tr(
                                                                                          "Turn Bluetooth on to manage devices") :
                                                                                      root.query.length
                                                                                      ? Translation.tr(
                                                                                            "No matching devices") :
                                                                                        Translation.tr(
                                                                                            "Search for nearby devices to pair them")
                wrapMode: Text.WordWrap
                color: Appearance.colors.colSubtext
            }
        }
    }
}
