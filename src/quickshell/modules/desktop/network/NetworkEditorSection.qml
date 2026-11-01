pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.settings
import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import qs.modules.shared
import qs.modules.shared.widgets

SettingsCard {
    id: root
    required property string title
    property string description: ""
    property string icon: "tune"
    default property alias contentData: fields.data
    Layout.fillWidth: true
    implicitHeight: body.implicitHeight + 28
    ColumnLayout {
        id: body
        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 14 }
        spacing: 12
        RowLayout {
            Layout.fillWidth: true
            MaterialSymbol { text: root.icon; iconSize: 22; color: Appearance.colors.colPrimary }
            StyledText { Layout.fillWidth: true; text: root.title; font.weight: Font.DemiBold; wrapMode: Text.WordWrap }
        }
        StyledText { Layout.fillWidth: true; visible: text.length > 0; text: root.description; wrapMode: Text.WordWrap; font.pixelSize: Appearance.font.pixelSize.smaller; color: Appearance.colors.colSubtext }
        ColumnLayout { id: fields; Layout.fillWidth: true; spacing: 8 }
    }
}
