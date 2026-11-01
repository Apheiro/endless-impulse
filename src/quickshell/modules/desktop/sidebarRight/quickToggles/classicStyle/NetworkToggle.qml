import qs.modules.shared.primitives.common
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets
import qs.modules.shared.functions
import qs.modules.desktop.sidebarRight.quickToggles
import qs
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland

QuickToggleButton {
    id:root
    toggled: Network.wifiStatus !== "disabled"
    buttonIcon: Network.materialSymbol
    onClicked: Network.toggleWifi()
    altAction: () => {
        NetworkControl.open(root.QsWindow.window?.screen?.name, Network.ethernet?"devices":"wifi")
        GlobalStates.sidebarRightOpen = false
    }
    StyledToolTip {
        text: Translation.tr("%1 | Right-click to configure").arg(Network.networkName)
    }
}
