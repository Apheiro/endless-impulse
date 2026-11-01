import QtQuick
import qs.modules.shared

Item {
    implicitWidth: 1
    implicitHeight: Appearance.sizes.baseBarHeight
    Rectangle {
        anchors.centerIn: parent
        width: 1; height: parent.height * .45
        color: Appearance.colors.colOutlineVariant
    }
}
