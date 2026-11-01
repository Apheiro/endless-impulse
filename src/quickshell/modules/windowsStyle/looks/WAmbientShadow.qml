pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Hyprland
import qs.modules.shared
import qs.modules.shared.functions
import qs.modules.windowsStyle.looks

Rectangle {
    id: root

    required property var target
    z: 0

    anchors {
        fill: target
        margins: -border.width
    }

    border.color: Looks.colors.ambientShadow
    border.width: 1
    color: "transparent"
    radius: target.radius + border.width
}
