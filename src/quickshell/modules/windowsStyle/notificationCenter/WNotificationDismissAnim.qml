import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import qs.modules.shared
import qs.modules.shared.widgets
import qs.modules.shared.functions
import qs.modules.windowsStyle.looks

SequentialAnimation {
    id: root

    required property var target

    PropertyAction {
        target: root.target
        property: "ListView.delayRemove"
        value: true
    }
    NumberAnimation {
        target: root.target
        property: "x"
        to: root.target.width
        duration: Appearance.animationDuration(250)
        easing.type: Easing.BezierSpline
        easing.bezierCurve: Looks.transition.easing.bezierCurve.easeIn
    }
    PropertyAction {
        target: root.target
        property: "ListView.delayRemove"
        value: false
    }
}
