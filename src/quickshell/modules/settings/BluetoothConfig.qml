import QtQuick
import qs.services
import qs.modules.desktop.bluetooth

Item {
    Component.onCompleted: BluetoothManager.open()
    Component.onDestruction: BluetoothManager.close()
    BluetoothPanelContent {
        anchors.fill: parent
        anchors.margins: 20
        embedded: true
    }
}
