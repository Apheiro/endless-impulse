import qs.modules.shared.primitives.settings
import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import qs.modules.shared
import qs.modules.shared.widgets

SettingsCard {
    id: root
    property string title
    property string icon: ""
    property bool showHeader: true
    default property alias contentData: sectionContent.data

    Layout.fillWidth: true
    implicitHeight: sectionLayout.implicitHeight + 32

    ColumnLayout {
        id: sectionLayout
        anchors {
            left: parent.left
            right: parent.right
            top: parent.top
            margins: 16
        }
        spacing: 16

        RowLayout {
            visible: root.showHeader
            Layout.fillWidth: true
            spacing: 10
            MaterialSymbol {
                visible: root.icon !== ""
                text: root.icon
                iconSize: 22
                color: Appearance.colors.colPrimary
            }
            StyledText {
                Layout.fillWidth: true
                text: root.title
                wrapMode: Text.WordWrap
                font.pixelSize: Appearance.font.pixelSize.larger
                font.weight: Font.Medium
                color: Appearance.colors.colOnLayer0
            }
        }

        ColumnLayout {
            id: sectionContent
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            Layout.maximumWidth: sectionLayout.width
            spacing: 8
        }
    }
}
