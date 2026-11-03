import qs.modules.shared.primitives.common
import qs.modules.shared
import qs.modules.shared.widgets
import QtQuick

GroupButton {
    id: button
    property string iconSource: ""
    property string buttonIcon
    baseWidth: 40
    baseHeight: 40
    clickedWidth: baseWidth + 20
    toggled: false
    buttonRadius: (altAction && toggled) ? Appearance?.rounding.normal : Math.min(baseHeight, baseWidth) / 2
    buttonRadiusPressed: Appearance?.rounding?.small

    contentItem: Item {
        Loader {
            anchors.centerIn: parent
            active: !!button.iconSource
            width: 22
            height: 22
            sourceComponent: CustomIcon {
                anchors.fill: parent
                source: button.iconSource
                colorize: true
                color: button.toggled ? Appearance.m3colors.m3onPrimary : Appearance.colors.colOnLayer1
            }
        }
        MaterialSymbol {
            visible: !button.iconSource
            anchors.centerIn: parent
            iconSize: 22
            fill: button.toggled ? 1 : 0
            color: button.toggled ? Appearance.m3colors.m3onPrimary : Appearance.colors.colOnLayer1
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            text: button.buttonIcon
            Behavior on color {
                animation: Appearance.animation.elementMoveFast.colorAnimation.createObject(this)
            }
        }
    }
}
