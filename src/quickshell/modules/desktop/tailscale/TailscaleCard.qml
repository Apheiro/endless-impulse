pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import Quickshell
import qs.services
import qs.modules.shared
import qs.modules.shared.primitives.common
import qs.modules.shared.widgets
import qs.modules.shared.primitives.settings

SettingsCard {
    id: root
    default property alias content: body.data
    property string title: ""
    property string subtitle: ""
    property string icon: ""
    property int padding: 16
    Layout.fillWidth: true
    implicitHeight: contentColumn.implicitHeight + padding * 2
    ColumnLayout {
        id: contentColumn
        anchors { left: parent.left; right: parent.right; top: parent.top; margins: root.padding }
        spacing: 14
        RowLayout {
            visible: !!root.title
            Layout.fillWidth: true
            spacing: 10
            MaterialSymbol { visible: !!root.icon; text: root.icon; iconSize: 22; color: Appearance.colors.colPrimary }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 3
                StyledText { Layout.fillWidth: true; text: root.title; textFormat: Text.PlainText; font.weight: Font.DemiBold; elide: Text.ElideRight }
                StyledText { visible: !!root.subtitle; Layout.fillWidth: true; text: root.subtitle; textFormat: Text.PlainText; wrapMode: Text.WordWrap; color: Appearance.colors.colSubtext; font.pixelSize: Appearance.font.pixelSize.smaller }
            }
        }
        ColumnLayout { id: body; Layout.fillWidth: true; spacing: 12 }
    }
}
