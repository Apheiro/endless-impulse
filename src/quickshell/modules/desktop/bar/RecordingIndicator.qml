import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets

RowLayout {
    id: root
    property color foreground: Appearance.colors.colOnLayer2
    visible: ScreenRecorder.active
    spacing: 6
    Rectangle {
        id: recordingDot
        implicitWidth: 7; implicitHeight: 7; radius: 4
        color: "#ff5252"
        SequentialAnimation on opacity {
            running: ScreenRecorder.recording && !ScreenRecorder.paused
            loops: Animation.Infinite
            NumberAnimation { to: 0.25; duration: Appearance.animationDuration(550) }
            NumberAnimation { to: 1; duration: Appearance.animationDuration(550) }
            onStopped: recordingDot.opacity = 1
        }
    }
    StyledText {
        text: ScreenRecorder.state.phase === "starting" ? "…" : ScreenRecorder.state.phase === "stopping" ? Translation.tr("Saving…") : ScreenRecorder.elapsedText
        color: root.foreground
        font.pixelSize: Appearance.font.pixelSize.small
        font.family: Appearance.font.family.numbers
    }
}
