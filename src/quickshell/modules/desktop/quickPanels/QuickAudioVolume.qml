pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets

ColumnLayout {
    id: root
    required property var entry
    property string label: entry.name
    Layout.fillWidth: true
    spacing: 2
    RowLayout {
        Layout.fillWidth: true
        StyledText { Layout.fillWidth: true; text: root.label; textFormat: Text.PlainText; elide: Text.ElideRight; font.pixelSize: Appearance.font.pixelSize.small }
        RippleButtonWithIcon {
            materialIcon: root.entry.muted ? "volume_off" : "volume_up"
            mainText: ""
            enabled: root.entry.volumeEffective !== false
            onClicked: AudioControl.objectAction("mute", root.entry, !root.entry.muted)
        }
    }
    RowLayout {
        Layout.fillWidth: true
        StyledSlider {
            id: slider
            Layout.fillWidth: true
            from: 0
            to: Math.max(root.entry.volume, Config.options.audio.protection.enable && root.entry.default ? Math.min(100, Config.options.audio.protection.maxAllowed) : 100)
            stepSize: 1
            enabled: root.entry.volumeEffective !== false
            configuration: StyledSlider.Configuration.S
            usePercentTooltip: false
            tooltipContent: Math.round(value) + "%"
            onMoved: AudioControl.objectAction("volume", root.entry, Math.round(value))
            Binding { target: slider; property: "value"; value: AudioControl.previewVolume(root.entry, -1); when: !slider.pressed }
        }
        StyledText { Layout.preferredWidth: 42; text: Math.round(slider.value) + "%"; horizontalAlignment: Text.AlignRight; font.pixelSize: Appearance.font.pixelSize.small; color: Appearance.colors.colSubtext }
    }
}
