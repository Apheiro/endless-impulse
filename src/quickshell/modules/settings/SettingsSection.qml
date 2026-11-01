import QtQuick
import QtQuick.Layouts
import qs.modules.common
import qs.modules.common.widgets

Rectangle {
    id: root
    property string title
    property string icon: ""
    default property alias contentData: sectionContent.data

    Layout.fillWidth: true
    implicitHeight: sectionLayout.implicitHeight + 32
    radius: Appearance.rounding.large
    color: Appearance.m3colors.m3surfaceContainer

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
