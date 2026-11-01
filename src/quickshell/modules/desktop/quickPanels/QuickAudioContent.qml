pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets

ColumnLayout {
    id: root
    objectName: "quick-content-audio"
    readonly property var output: AudioControl.entries(AudioControl.outputs).find(item => item.default) || null
    spacing: 10
    Loader {
        Layout.fillWidth: true
        active: root.output !== null
        sourceComponent: QuickAudioVolume { entry: root.output; label: Translation.tr("General volume") + " · " + AudioControl.deviceLabel(entry, false) }
    }
    StyledText { visible: !AudioControl.loaded || AudioControl.failed; Layout.fillWidth: true; text: AudioControl.failed ? AudioControl.message : Translation.tr("Connecting to PipeWire…"); wrapMode: Text.WordWrap; color: Appearance.colors.colSubtext }
    StyledText { text: Translation.tr("Applications"); color: Appearance.colors.colSubtext; font.pixelSize: Appearance.font.pixelSize.smaller }
    StyledFlickable {
        Layout.fillWidth: true
        Layout.fillHeight: true
        implicitHeight: Math.min(280, apps.implicitHeight)
        contentHeight: apps.implicitHeight
        clip: true
        ColumnLayout {
            id: apps
            width: parent.width
            spacing: 8
            Repeater { model: AudioControl.playback; delegate: QuickAudioVolume {} }
            StyledText { visible: AudioControl.playback.count === 0; text: Translation.tr("No applications playing audio"); color: Appearance.colors.colSubtext; font.pixelSize: Appearance.font.pixelSize.small }
        }
    }
}
