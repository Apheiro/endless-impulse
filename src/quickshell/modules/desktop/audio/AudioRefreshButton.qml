import qs.modules.shared.primitives.common
import QtQuick
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets

RippleButton {
    id: root
    objectName: "audio-refresh-button"
    implicitWidth: 34
    implicitHeight: 34
    padding: 0
    onClicked: AudioControl.refresh()
    contentItem: Item {
        Rectangle {
            id: pulse
            objectName: "audio-refresh-pulse"
            anchors.centerIn: parent
            width: 30
            height: width
            radius: width / 2
            color: "transparent"
            border.width: 1
            border.color: Appearance.colors.colPrimary
            opacity: AudioControl.refreshing ? 0.35 : 0
            Behavior on opacity {
                NumberAnimation {
                    duration: Appearance.animation.elementMoveFast.duration
                }
            }
            SequentialAnimation on scale {
                running: AudioControl.refreshing && AudioControl.opened
                loops: Animation.Infinite
                NumberAnimation {
                    from: 0.72
                    to: 1
                    duration: Appearance.animationDuration(1000)
                    easing.type: Easing.InOutSine
                }
                NumberAnimation {
                    from: 1
                    to: 0.72
                    duration: Appearance.animationDuration(1000)
                    easing.type: Easing.InOutSine
                }
            }
        }
        MaterialSymbol {
            anchors.centerIn: parent
            text: "refresh"
            iconSize: 22
        }
    }
    property var tooltip: StyledToolTip {
        text: Translation.tr("Refresh audio devices")
    }
}
