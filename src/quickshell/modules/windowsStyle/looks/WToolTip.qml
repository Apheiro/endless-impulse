import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import qs.modules.shared
import qs.modules.shared.functions
import qs.modules.shared.widgets
import qs.modules.windowsStyle.looks

StyledToolTip {
    id: root

    required property Item realContentItem
    font {
        family: Looks.font.family.ui
        pixelSize: Looks.font.pixelSize.normal
        weight: Looks.font.weight.regular
    }
    realContentItem: WText {
        text: root.text
        font: root.font
        anchors.centerIn: parent
    }

    verticalPadding: 8
    horizontalPadding: 10

    delay: 400

    contentItem: WToolTipContent {
        id: tooltipContent
        realContentItem: root.realContentItem
        horizontalPadding: root.horizontalPadding
        verticalPadding: root.verticalPadding
    }
}
