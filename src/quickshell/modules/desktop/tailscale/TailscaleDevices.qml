pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import Quickshell
import qs.services
import qs.modules.shared
import qs.modules.shared.primitives.common
import qs.modules.shared.widgets
ColumnLayout {
    id: root
    property bool onlineOnly: false
    readonly property var devices: TailscaleControl.state.peers.filter(p => (!onlineOnly || p.online) && (p.name + " " + p.dns + " " + p.ips.join(" ")).toLowerCase().includes(search.text.toLowerCase()))
    function deviceIcon(os) {
        return ({linux: "computer", windows: "desktop_windows", macOS: "laptop_mac", iOS: "phone_iphone", android: "phone_android", freebsd: "dns"})[os] || "devices_other";
    }
    spacing: 12
    RowLayout {
        Layout.fillWidth: true; spacing: 10
        MaterialTextField { id: search; Layout.fillWidth: true; placeholderText: Translation.tr("Search by name or IP address"); wrapMode: TextInput.NoWrap }
        RippleButtonWithIcon { materialIcon: "filter_alt"; mainText: Translation.tr("Online only"); toggled: root.onlineOnly; onClicked: root.onlineOnly = !root.onlineOnly }
        TailscaleBadge { text: root.devices.length + " " + Translation.tr("devices"); icon: "devices" }
    }
    TailscaleCard {
        title: Translation.tr("Tailnet devices")
        subtitle: Translation.tr("Copy an address or check the connection to a peer")
        icon: "device_hub"
        Repeater {
            model: root.devices
            RowLayout {
                id: device
                required property var modelData
                Layout.fillWidth: true; spacing: 12
                Rectangle {
                    implicitWidth: 42; implicitHeight: 42
                    radius: Appearance.rounding.small
                    color: device.modelData.online ? Appearance.colors.colSecondaryContainer : Appearance.colors.colLayer2
                    MaterialSymbol { anchors.centerIn: parent; text: root.deviceIcon(device.modelData.os); iconSize: 23; color: device.modelData.online ? Appearance.colors.colOnSecondaryContainer : Appearance.colors.colOnLayer2 }
                }
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 3
                    RowLayout {
                        Layout.fillWidth: true
                        StyledText { Layout.fillWidth: true; text: device.modelData.name; textFormat: Text.PlainText; elide: Text.ElideRight; font.weight: Font.DemiBold }
                        MaterialSymbol { visible: device.modelData.exitOption; text: "alt_route"; iconSize: 17; color: Appearance.colors.colSubtext }
                    }
                    StyledText { Layout.fillWidth: true; text: device.modelData.ips.join(" · "); textFormat: Text.PlainText; elide: Text.ElideRight; color: Appearance.colors.colSubtext; font.pixelSize: Appearance.font.pixelSize.smaller; font.family: Appearance.font.family.numbers }
                }
                TailscaleBadge { visible: root.width >= 600; text: device.modelData.online ? Translation.tr("Online") : Translation.tr("Offline"); icon: device.modelData.online ? "check_circle" : "schedule"; highlighted: device.modelData.online }
                RippleButtonWithIcon { materialIcon: "content_copy"; mainText: ""; enabled: device.modelData.ips.length > 0; onClicked: Quickshell.clipboardText = device.modelData.ips[0]; Accessible.name: Translation.tr("Copy address") }
                RippleButtonWithIcon { materialIcon: "network_ping"; mainText: root.width >= 600 ? Translation.tr("Ping") : ""; enabled: !TailscaleControl.busy && device.modelData.ips.length > 0; onClicked: TailscaleControl.run(["ping"], {c: "3"}, [device.modelData.ips[0]]); Accessible.name: Translation.tr("Ping") }
            }
        }
        ColumnLayout {
            visible: root.devices.length === 0
            Layout.fillWidth: true; Layout.topMargin: 16; Layout.bottomMargin: 16
            MaterialSymbol { Layout.alignment: Qt.AlignHCenter; text: "devices_other"; iconSize: 40; color: Appearance.colors.colSubtext }
            StyledText { Layout.alignment: Qt.AlignHCenter; text: Translation.tr("No matching devices"); color: Appearance.colors.colSubtext }
        }
    }
}
