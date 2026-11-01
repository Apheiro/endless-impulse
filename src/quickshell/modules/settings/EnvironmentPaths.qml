pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import Quickshell
import qs.services
import qs.modules.common
import qs.modules.common.widgets

ColumnLayout {
    id: root
    property var entries: IconTheme.paths
    property bool expanded: false
    Layout.fillWidth: true
    spacing: 4
    RippleButtonWithIcon {
        Layout.fillWidth: true
        materialIcon: root.expanded ? "expand_less" : "expand_more"
        mainText: Translation.tr("Environments & paths")
        onClicked: root.expanded = !root.expanded
    }
    Loader {
        active: root.expanded
        visible: active
        Layout.fillWidth: true
        Layout.preferredHeight: item ? item.implicitHeight : 0
        sourceComponent: ColumnLayout {
            spacing: 2
            Repeater {
                model: root.entries
                delegate: RippleButton {
                    id: entry
                    required property var modelData
                    Layout.fillWidth: true
                    implicitHeight: contentItem.implicitHeight + 16
                    enabled: modelData.exists
                    onClicked: Qt.openUrlExternally("file://" + encodeURI(modelData.path).replace(/#/g, "%23").replace(/\?/g, "%3F"))
                    contentItem: ColumnLayout {
                        StyledText { text: entry.modelData.name; font.pixelSize: Appearance.font.pixelSize.small }
                        StyledText {
                            id: pathLabel
                            Layout.fillWidth: true
                            text: entry.modelData.path + (entry.modelData.value ? "  ·  " + entry.modelData.value : "")
                            color: Appearance.colors.colSubtext
                            font.pixelSize: Appearance.font.pixelSize.smaller
                            wrapMode: Text.WrapAnywhere
                        }
                    }
                    StyledToolTip { text: Translation.tr("Open configuration file") }
                }
            }
        }
    }
}
