import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets

ColumnLayout {
    id: root
    required property string label
    property string description: ""
    required property real value
    required property real defaultValue
    signal edited(real duration)
    Layout.fillWidth: true
    Layout.minimumWidth: 0
    spacing: 4
    SettingsRange {
        text: root.label
        value: root.value
        from: 10
        to: 10000
        stepSize: 10
        decimals: 0
        suffix: "ms"
        onEdited: nextValue => root.edited(nextValue)
    }
    StyledText {
        Layout.fillWidth: true
        visible: root.description.length > 0
        text: root.description
        wrapMode: Text.WordWrap
        font.pixelSize: Appearance.font.pixelSize.smaller
        color: Appearance.colors.colSubtext
    }
    RowLayout {
        Layout.fillWidth: true
        StyledText {
            Layout.fillWidth: true
            text: Translation.tr("At current speed: %1 ms").arg(Math.round(root.value / Appearance.animationSpeed))
            font.pixelSize: Appearance.font.pixelSize.smaller
            color: Appearance.colors.colSubtext
        }
        RippleButtonWithIcon {
            materialIcon: "restart_alt"
            mainText: ""
            enabled: root.value !== root.defaultValue
            Accessible.name: Translation.tr("Restore default duration")
            onClicked: root.edited(root.defaultValue)
        }
    }
}
