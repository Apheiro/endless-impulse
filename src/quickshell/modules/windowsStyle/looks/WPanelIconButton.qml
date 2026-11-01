import QtQuick
import Quickshell
import qs
import qs.services
import qs.modules.shared
import qs.modules.windowsStyle.looks
import qs.modules.windowsStyle.bar

WButton {
    id: root

    property alias iconName: iconContent.icon
    property alias iconSize: iconContent.implicitSize
    property alias monochrome: iconContent.monochrome
    implicitWidth: 40
    implicitHeight: 40

    contentItem: Item {
        FluentIcon {
            id: iconContent
            anchors.centerIn: parent
            implicitSize: 18
            icon: root.iconName
        }
    }
}
