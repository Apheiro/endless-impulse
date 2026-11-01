import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import qs.modules.shared
import qs.modules.shared.widgets

RippleButton {
    id: buttonWithIconRoot
    readonly property color foregroundColor: toggled ? Appearance.m3colors.m3onPrimary : Appearance.colors.colOnLayer0
    property string nerdIcon
    property string materialIcon
    property bool materialIconFill: true
    property string mainText: "Button text"
    property Component mainContentComponent: Component {
        StyledText {
            visible: text !== ""
            text: buttonWithIconRoot.mainText
            font.pixelSize: Appearance.font.pixelSize.small
            color: buttonWithIconRoot.foregroundColor
        }
    }
    implicitHeight: 35
    horizontalPadding: 10
    buttonRadius: Appearance.rounding.small
    colBackground: Appearance.colors.colLayer2

    contentItem: RowLayout {
        Item {
            Layout.fillWidth: false
            implicitWidth: Math.max(materialIconLoader.implicitWidth, nerdIconLoader.implicitWidth)
            Loader {
                id: materialIconLoader
                anchors.centerIn: parent
                active: !nerdIcon
                sourceComponent: MaterialSymbol {
                    text: buttonWithIconRoot.materialIcon
                    iconSize: Appearance.font.pixelSize.larger
                    color: buttonWithIconRoot.foregroundColor
                    fill: buttonWithIconRoot.materialIconFill ? 1 : 0
                }
            }
            Loader {
                id: nerdIconLoader
                anchors.centerIn: parent
                active: nerdIcon
                sourceComponent: StyledText {
                    text: buttonWithIconRoot.nerdIcon
                    font.pixelSize: Appearance.font.pixelSize.larger
                    font.family: Appearance.font.family.iconNerd
                    color: buttonWithIconRoot.foregroundColor
                }
            }
        }
        Loader {
            Layout.fillWidth: true
            sourceComponent: buttonWithIconRoot.mainContentComponent
            Layout.alignment: Qt.AlignVCenter
        }
    }
}
