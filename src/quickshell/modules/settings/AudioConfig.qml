import QtQuick
import qs.services
import qs.modules.desktop.audio

Item {
    Component.onCompleted: AudioControl.open()
    Component.onDestruction: AudioControl.close()
    AudioPanelContent {
        anchors.fill: parent
        anchors.margins: 20
        embedded: true
    }
}
