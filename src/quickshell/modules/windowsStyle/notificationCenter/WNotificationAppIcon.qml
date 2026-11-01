import QtQuick
import QtQuick.Layouts
import Quickshell
import org.kde.kirigami as Kirigami
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets
import qs.modules.shared.functions
import qs.modules.windowsStyle.looks

Item {
    id: root

    property string icon: ""
    property real implicitSize: 16
    implicitWidth: implicitSize
    implicitHeight: implicitSize

    Kirigami.Icon {
        anchors.fill: parent
        implicitWidth: root.implicitSize
        implicitHeight: root.implicitSize

        source: root.icon || fallback
        fallback: `${Looks.iconsPath}/apps.svg`
        roundToIconSize: false
        isMask: !root.icon
        color: Looks.colors.fg
    }
}
