import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import qs
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets
import qs.modules.desktop.audio
import qs.modules.desktop.quickPanels

RippleButton {
    id:root
    implicitWidth: row.implicitWidth+20
    implicitHeight: row.implicitHeight+10
    buttonRadius: Appearance.rounding.full
    toggled: GlobalStates.sidebarRightOpen || QuickPanelState.section !== ""
    colBackground:"transparent"
    readonly property color foreground: toggled?Appearance.colors.colOnSecondaryContainer:Appearance.colors.colOnLayer0
    onClicked: QuickPanelState.toggleSidebar()
    RowLayout {
        id:row;anchors.centerIn:parent;spacing:Appearance.sizes.statusIconSpacing
        Revealer {
            reveal:Notifications.silent||Notifications.unread>0
            Item {implicitWidth:Appearance.sizes.statusIconWidth;implicitHeight:Appearance.sizes.statusIconHeight;NotificationUnreadCount{anchors.centerIn:parent;color:root.foreground}}
        }
        AudioPanelButton {surfaceVisible:false;foreground:root.foreground;Layout.alignment:Qt.AlignVCenter}
        Revealer {
            reveal:Audio.source?.audio?.muted??false
            Item{implicitWidth:Appearance.sizes.statusIconWidth;implicitHeight:Appearance.sizes.statusIconHeight;MaterialSymbol{anchors.centerIn:parent;text:"mic_off";iconSize:Appearance.font.pixelSize.larger;color:root.foreground}}
        }
        HyprlandXkbIndicator{Layout.alignment:Qt.AlignVCenter;Layout.preferredWidth:Appearance.sizes.statusIconWidth;Layout.preferredHeight:Appearance.sizes.statusIconHeight;color:root.foreground}
        StatusPanelButton{surfaceVisible:false;foreground:root.foreground;section:"network";materialIcon:Network.materialSymbol}
        StatusPanelButton{surfaceVisible:false;foreground:root.foreground;visible:BluetoothStatus.available;section:"bluetooth";materialIcon:BluetoothStatus.connected?"bluetooth_connected":BluetoothStatus.enabled?"bluetooth":"bluetooth_disabled"}
    }
}
