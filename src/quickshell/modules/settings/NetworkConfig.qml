import QtQuick
import qs.services
import qs.modules.desktop.network

Item {
    Component.onCompleted: NetworkControl.open()
    Component.onDestruction: NetworkControl.close()
    NetworkPanelContent {
        anchors.fill: parent
        anchors.margins: 20
        embedded: true
    }
}
