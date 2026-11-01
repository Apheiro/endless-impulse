import qs.modules.shared.primitives.common
import qs
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets
import qs.modules.shared.functions
import QtQuick
import Quickshell
import Quickshell.Bluetooth
import Quickshell.Io
import Quickshell.Hyprland

QuickToggleButton {
    id: root
    visible: BluetoothStatus.available
    toggled: BluetoothStatus.enabled
    buttonIcon: BluetoothStatus.connected ? "bluetooth_connected" : BluetoothStatus.enabled ? "bluetooth" : "bluetooth_disabled"
    onClicked: {
        Bluetooth.defaultAdapter.enabled = !Bluetooth.defaultAdapter?.enabled
    }
    altAction: () => {
        BluetoothManager.open(root.QsWindow.window?.screen?.name)
        GlobalStates.sidebarRightOpen = false
    }
    StyledToolTip {
        text: Translation.tr("%1 | Right-click to configure").arg(
            (BluetoothStatus.firstActiveDevice?.name ?? Translation.tr("Bluetooth"))
            + (BluetoothStatus.activeDeviceCount > 1 ? ` +${BluetoothStatus.activeDeviceCount - 1}` : "")
            )
    }
}
