pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.settings
import qs.modules.shared.primitives.common
import QtQuick
import Quickshell
import QtQuick.Layouts
import Quickshell.Bluetooth
import qs.services
import qs.modules.shared
import qs.modules.shared.functions
import qs.modules.shared.widgets

SettingsCard {
    id: root
    objectName: "bluetooth-device-card"
    required property var device
    property bool expanded: false
    property bool confirmForget: false
    readonly property bool pairing: device.pairing || BluetoothManager.pairing(device.dbusPath)
    readonly property string action: BluetoothManager.actionFor(device.dbusPath)
    readonly property bool busy: BluetoothManager.pending(device.dbusPath) || pairing || device.state
                                 === BluetoothDeviceState.Connecting || device.state
                                 === BluetoothDeviceState.Disconnecting
    readonly property string statusText: {
        if (device.blocked) return Translation.tr("Blocked");
        if (pairing) return Translation.tr("Pairing…");
        if (action === "disconnect" || device.state === BluetoothDeviceState.Disconnecting) return Translation.tr("Disconnecting…");
        if (action === "connect" || device.state === BluetoothDeviceState.Connecting) return Translation.tr("Connecting…");
        if (busy) return Translation.tr("Working…");
        return device.connected ? Translation.tr("Connected") : device.paired ? Translation.tr("Paired") : Translation.tr("Available to pair");
    }
    Layout.fillWidth: true
    implicitHeight: body.implicitHeight + 28
    emphasized: device.connected
    ColumnLayout {
        id: body
        anchors {
            left: parent.left
            right: parent.right
            top: parent.top
            margins: 14
        }
        spacing: 10
        RowLayout {
            Layout.fillWidth: true
            MaterialSymbol {
                text: Icons.getBluetoothDeviceMaterialSymbol(root.device.icon || "")
                iconSize: 30
                color: Appearance.colors.colPrimary
            }
            ColumnLayout {
                Layout.fillWidth: true
                StyledText {
                    Layout.fillWidth: true
                    text: root.device.name
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                    font.weight: Font.Medium
                }
                StyledText {
                    Layout.fillWidth: true
                    text: root.statusText
                    color: Appearance.colors.colSubtext
                    font.pixelSize: Appearance.font.pixelSize.smaller
                }
            }
            StyledText {
                visible: root.device.batteryAvailable
                text: Math.round(root.device.battery * 100) + "%"
                color: Appearance.colors.colPrimary
                font.family: Appearance.font.family.numbers
            }
            RippleButtonWithIcon {
                visible: !root.busy
                materialIcon: root.device.connected ? "link_off" : "link"
                mainText: root.device.connected ? Translation.tr("Disconnect") : root.device.paired
                                                  ? Translation.tr("Connect") : Translation.tr(
                                                        "Pair & connect")
                enabled: BluetoothManager.agentReady && !root.device.blocked
                onClicked: BluetoothManager.command(root.device.connected ? "disconnect" : root.device.paired
                                                                            ? "connect" : "pair",
                                                    root.device.dbusPath)
            }
            RippleButtonWithIcon {
                visible: root.busy && root.pairing
                materialIcon: "close"
                mainText: Translation.tr("Cancel")
                onClicked: BluetoothManager.command("cancel", root.device.dbusPath)
            }
            RippleButtonWithIcon {
                materialIcon: root.expanded ? "expand_less" : "expand_more"
                mainText: ""
                onClicked: root.expanded = !root.expanded
            }
        }
        ColumnLayout {
            visible: root.expanded
            Layout.fillWidth: true
            StyledText {
                Layout.fillWidth: true
                text: root.device.address
                font.family: Appearance.font.family.monospace
                font.pixelSize: Appearance.font.pixelSize.smaller
                color: Appearance.colors.colSubtext
            }
            RowLayout {
                Layout.fillWidth: true
                MaterialTextField {
                    id: alias
                    Layout.fillWidth: true
                    maximumLength: 248
                    Component.onCompleted: text = root.device.name
                    placeholderText: Translation.tr("Device name")
                }
                RippleButtonWithIcon {
                    materialIcon: "edit"
                    mainText: Translation.tr("Rename")
                    enabled: alias.text.trim().length > 0
                    onClicked: root.device.name = alias.text.trim()
                }
            }
            Flow {
                Layout.fillWidth: true
                spacing: 6
                RippleButtonWithIcon {
                    materialIcon: root.device.trusted ? "verified_user" : "shield"
                    mainText: Translation.tr("Trusted")
                    toggled: root.device.trusted
                    onClicked: root.device.trusted = !root.device.trusted
                }
                RippleButtonWithIcon {
                    materialIcon: "block"
                    mainText: Translation.tr("Blocked")
                    toggled: root.device.blocked
                    onClicked: root.device.blocked = !root.device.blocked
                }
                RippleButtonWithIcon {
                    materialIcon: "bedtime_off"
                    mainText: Translation.tr("Wake computer")
                    toggled: root.device.wakeAllowed
                    onClicked: root.device.wakeAllowed = !root.device.wakeAllowed
                }
                RippleButtonWithIcon {
                    visible: Config.options.panelFamily === "ii" && root.device.connected
                             && (root.device.icon || "").startsWith("audio")
                    materialIcon: "graphic_eq"
                    mainText: Translation.tr("Audio profiles")
                    onClicked: {
                        const screen = root.QsWindow.window?.screen?.name;
                        BluetoothManager.close();
                        SettingsNavigation.open("audio", "profiles");
                    }
                }
                RippleButtonWithIcon {
                    visible: root.device.paired
                    materialIcon: "delete"
                    mainText: Translation.tr("Forget device")
                    enabled: !root.busy
                    onClicked: root.confirmForget = !root.confirmForget
                }
            }
            StyledText {
                Layout.fillWidth: true
                visible: root.confirmForget
                text: Translation.tr("Forget this device? You will need to pair it again.")
                wrapMode: Text.WordWrap
                color: Appearance.colors.colPrimary
            }
            RowLayout {
                visible: root.confirmForget
                RippleButtonWithIcon {
                    materialIcon: "close"
                    mainText: Translation.tr("Cancel")
                    onClicked: root.confirmForget = false
                }
                RippleButtonWithIcon {
                    materialIcon: "delete_forever"
                    mainText: Translation.tr("Forget")
                    enabled: BluetoothManager.agentReady
                    onClicked: {
                        BluetoothManager.command("forget", root.device.dbusPath);
                        root.confirmForget = false;
                    }
                }
            }
        }
    }
}
