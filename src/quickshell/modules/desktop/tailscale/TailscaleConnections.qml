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
    readonly property var current: TailscaleControl.state.profiles.find(p => p.selected) || ({})
    readonly property int onlineCount: TailscaleControl.state.peers.filter(p => p.online).length
    spacing: 12
    TailscaleCard {
        emphasized: true
        RowLayout {
            Layout.fillWidth: true
            spacing: 16
            Rectangle {
                implicitWidth: 64; implicitHeight: 64
                radius: Appearance.rounding.normal
                color: TailscaleControl.state.running ? Appearance.colors.colPrimaryContainer : Appearance.colors.colLayer2
                CustomIcon { anchors.centerIn: parent; source: "tailscale-symbolic.svg"; width: 36; height: 36; colorize: true; color: TailscaleControl.state.running ? Appearance.colors.colOnPrimaryContainer : Appearance.colors.colOnLayer2 }
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 5
                StyledText { Layout.fillWidth: true; text: TailscaleControl.state.hostname || Translation.tr("This device"); textFormat: Text.PlainText; font.pixelSize: Appearance.font.pixelSize.larger; font.weight: Font.DemiBold; elide: Text.ElideRight }
                StyledText { Layout.fillWidth: true; text: TailscaleControl.state.tailnet || root.current.tailnet || Translation.tr("Your private network"); textFormat: Text.PlainText; elide: Text.ElideRight; color: Appearance.colors.colSubtext }
                Flow {
                    Layout.fillWidth: true; spacing: 6
                    TailscaleBadge { text: TailscaleControl.state.running ? Translation.tr("Connected") : Translation.tr("Disconnected"); icon: TailscaleControl.state.running ? "check_circle" : "link_off"; highlighted: TailscaleControl.state.running }
                    TailscaleBadge { text: root.onlineCount + " / " + TailscaleControl.state.peers.length + " " + Translation.tr("online"); icon: "devices" }
                }
            }
            RippleButtonWithIcon { materialIcon: TailscaleControl.state.running ? "power_settings_new" : "link"; mainText: TailscaleControl.state.running ? Translation.tr("Disconnect") : Translation.tr("Connect"); toggled: !TailscaleControl.state.running; enabled: TailscaleControl.state.installed && !TailscaleControl.busy; onClicked: TailscaleControl.toggle() }
        }
        Flow {
            Layout.fillWidth: true; spacing: 6
            Repeater {
                model: TailscaleControl.state.ips || []
                RippleButtonWithIcon {
                    required property string modelData
                    materialIcon: "content_copy"; mainText: modelData
                    onClicked: Quickshell.clipboardText = modelData
                    Accessible.name: Translation.tr("Copy address") + " " + modelData
                }
            }
        }
        Repeater { model: TailscaleControl.state.health || []; StyledText { required property string modelData; Layout.fillWidth: true; text: modelData; textFormat: Text.PlainText; wrapMode: Text.WordWrap; color: Appearance.colors.colError } }
        StyledText { visible: !TailscaleControl.state.installed; text: Translation.tr("Tailscale is not installed"); color: Appearance.colors.colError }
    }
    GridLayout {
        Layout.fillWidth: true
        columns: root.width >= 720 ? 2 : 1
        columnSpacing: 12; rowSpacing: 12
        TailscaleCard {
            Layout.alignment: Qt.AlignTop
            title: Translation.tr("Saved accounts")
            subtitle: Translation.tr("Choose the identity and tailnet for this device")
            icon: "manage_accounts"
            Repeater {
                model: TailscaleControl.state.profiles
                Rectangle {
                    id: account
                    required property var modelData
                    Layout.fillWidth: true
                    implicitHeight: accountRow.implicitHeight + 20
                    radius: Appearance.rounding.small
                    color: modelData.selected ? Appearance.colors.colSecondaryContainer : "transparent"
                    readonly property color foreground: modelData.selected ? Appearance.colors.colOnSecondaryContainer : Appearance.colors.colOnLayer0
                    RowLayout {
                        id: accountRow
                        anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; margins: 10 }
                        spacing: 10
                        MaterialSymbol { text: account.modelData.selected ? "account_circle" : "person_outline"; iconSize: 26; color: account.foreground }
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 2
                            StyledText { Layout.fillWidth: true; text: account.modelData.nickname || account.modelData.account || account.modelData.tailnet; textFormat: Text.PlainText; elide: Text.ElideRight; color: account.foreground; font.weight: Font.DemiBold }
                            StyledText { Layout.fillWidth: true; text: account.modelData.tailnet || account.modelData.account || ""; textFormat: Text.PlainText; elide: Text.ElideRight; color: account.foreground; font.pixelSize: Appearance.font.pixelSize.smaller }
                        }
                        MaterialSymbol { visible: account.modelData.selected; text: "check_circle"; iconSize: 20; color: account.foreground }
                        RippleButtonWithIcon { visible: !account.modelData.selected; materialIcon: "swap_horiz"; mainText: Translation.tr("Switch"); enabled: !TailscaleControl.busy; onClicked: TailscaleControl.switchTo(account.modelData) }
                    }
                }
            }
            RippleButtonWithIcon { Layout.fillWidth: true; materialIcon: "person_add"; mainText: Translation.tr("Add account"); enabled: !TailscaleControl.busy; onClicked: TailscaleControl.run(["login"], {timeout: "2m"}) }
            RippleButtonWithIcon { Layout.fillWidth: true; visible: !!TailscaleControl.state.authURL; materialIcon: "open_in_new"; mainText: Translation.tr("Open login page"); onClicked: TailscaleControl.openURL(TailscaleControl.state.authURL) }
        }
        TailscaleCard {
            Layout.alignment: Qt.AlignTop
            title: Translation.tr("Internet routing")
            subtitle: Translation.tr("Route internet traffic through another device")
            icon: "alt_route"
            StyledText { text: Translation.tr("Exit node"); font.weight: Font.Medium }
            StyledComboBox {
                Layout.fillWidth: true
                property var nodes: [{name: Translation.tr("Direct connection"), ip: ""}].concat(TailscaleControl.state.peers.filter(p => p.exitOption && p.ips.length).map(p => ({name: p.name + (p.online ? "" : " · " + Translation.tr("Offline")), ip: p.ips[0]})))
                model: nodes; textRole: "name"
                currentIndex: nodes.findIndex(n => n.ip === (TailscaleControl.state.prefs["exit-node"] || ""))
                enabled: !TailscaleControl.busy
                onActivated: index => TailscaleControl.setFlag("exit-node", nodes[index].ip)
            }
            TailscaleBadge { icon: TailscaleControl.state.prefs["exit-node"] ? "vpn_lock" : "public"; text: TailscaleControl.state.prefs["exit-node"] ? Translation.tr("Exit node in use") : Translation.tr("Using local internet"); highlighted: !!TailscaleControl.state.prefs["exit-node"] }
            TailscalePreference { preferenceKey: "exit-node-allow-lan-access"; label: Translation.tr("Local network access"); description: Translation.tr("Keep access to nearby devices while using an exit node"); icon: "lan" }
            TailscalePreference { preferenceKey: "advertise-exit-node"; label: Translation.tr("Offer this device as an exit node"); icon: "router" }
        }
    }
}
