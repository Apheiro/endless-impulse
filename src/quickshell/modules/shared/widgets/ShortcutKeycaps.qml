pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.common
import QtQuick
import "../functions/ShortcutSymbols.js" as ShortcutSymbols
import qs.services
import qs.modules.shared
import qs.modules.shared.functions

Item {
    id: root
    property string combination: ""
    property real pixelSize: 13
    implicitWidth: caps.implicitWidth
    implicitHeight: caps.implicitHeight
    Row {
        id: caps
        spacing: 3
        Repeater {
            model: ShortcutSymbols.tokens(root.combination, Config.options.cheatsheet)
            Row {
                required property var modelData
                anchors.verticalCenter: parent.verticalCenter
                StyledText {
                    visible: modelData.separator
                    text: "+"
                    font.pixelSize: root.pixelSize
                    color: Appearance.colors.colSubtext
                }
                KeyboardKey {
                    visible: !modelData.separator
                    key: modelData.text
                    pixelSize: root.pixelSize
                    horizontalPadding: 5
                }
            }
        }
    }
    MouseArea {
        id: hover
        anchors.fill: parent
        acceptedButtons: Qt.NoButton
        hoverEnabled: true
        StyledToolTip { text: root.combination; extraVisibleCondition: hover.containsMouse }
    }
}
