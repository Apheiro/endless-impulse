pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import Quickshell
import qs.services
import qs.modules.shared
import qs.modules.shared.primitives.common
import qs.modules.shared.widgets
Rectangle {
    id: root
    property string text: ""
    property string icon: ""
    property bool highlighted: false
    implicitWidth: content.implicitWidth + 18
    implicitHeight: content.implicitHeight + 10
    radius: Appearance.rounding.full
    color: highlighted ? Appearance.colors.colSecondaryContainer : Appearance.colors.colLayer2
    readonly property color foreground: highlighted ? Appearance.colors.colOnSecondaryContainer : Appearance.colors.colOnLayer2
    RowLayout {
        id: content
        anchors.centerIn: parent
        spacing: 5
        MaterialSymbol { visible: !!root.icon; text: root.icon; iconSize: 15; color: root.foreground }
        StyledText { text: root.text; textFormat: Text.PlainText; color: root.foreground; font.pixelSize: Appearance.font.pixelSize.smaller; font.weight: Font.Medium }
    }
}
