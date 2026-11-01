pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import qs.modules.shared
import qs.modules.shared.primitives.common

BarModuleBase {
    id: root
    property string icon: ""
    property string label: ""
    interactive: true
    RowLayout {
        anchors.centerIn: parent
        implicitHeight: Appearance.sizes.baseBarHeight
        spacing: 4
        MaterialSymbol { text: root.icon; iconSize: Appearance.font.pixelSize.larger; color: root.foreground }
        StyledText { visible: text.length > 0; text: root.label; font.pixelSize: Appearance.font.pixelSize.small; color: root.foreground }
    }
}
