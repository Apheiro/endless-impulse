import qs.modules.shared.primitives.common
import qs.modules.shared
import qs.modules.shared.widgets
import QtQuick

RippleButton {
    id: button
    surfaceVisible: false

    required default property Item content
    property bool extraActiveCondition: false

    implicitHeight: Math.max(content.implicitHeight, 26, content.implicitHeight)
    implicitWidth: implicitHeight
    contentItem: content

}
