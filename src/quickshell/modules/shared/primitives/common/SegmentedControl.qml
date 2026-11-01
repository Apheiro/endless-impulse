pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import qs.modules.shared

Rectangle {
    id: root
    required property var model
    property int currentIndex: 0
    signal activated(int index)
    implicitWidth: 540
    implicitHeight: 44
    radius: Appearance.rounding.full
    color: Appearance.colors.colBackgroundSurfaceContainer
    border.width: 1
    border.color: Appearance.colors.colLayer0Border
    function activate(index) {
        if (index < 0 || index >= model.length) return;
        activated(index);
        segments.itemAt(index)?.forceActiveFocus();
    }
    Keys.onLeftPressed: activate(currentIndex - 1)
    Keys.onRightPressed: activate(currentIndex + 1)
    RowLayout {
        anchors.fill: parent
        anchors.margins: 4
        spacing: 2
        uniformCellSizes: true
        Repeater {
            id: segments
            model: root.model
            delegate: RippleButton {
                id: segment
                required property int index
                required property var modelData
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumWidth: 0
                toggled: root.currentIndex === index
                buttonRadius: Appearance.rounding.full
                colBackgroundToggled: Appearance.colors.colSecondaryContainer
                colBackgroundToggledHover: Appearance.colors.colSecondaryContainerHover
                Accessible.role: Accessible.RadioButton
                Accessible.name: modelData.name
                Accessible.checked: toggled
                onClicked: root.activate(index)
                contentItem: RowLayout {
                    spacing: 6
                    MaterialSymbol { visible: root.width >= 380 && !!segment.modelData.icon; text: segment.modelData.icon || ""; iconSize: 19; color: segment.toggled ? Appearance.colors.colOnSecondaryContainer : Appearance.colors.colOnLayer0 }
                    StyledText { Layout.fillWidth: true; text: segment.modelData.name; elide: Text.ElideRight; horizontalAlignment: Text.AlignHCenter; font.pixelSize: Appearance.font.pixelSize.small; font.weight: segment.toggled ? Font.DemiBold : Font.Normal; color: segment.toggled ? Appearance.colors.colOnSecondaryContainer : Appearance.colors.colOnLayer0 }
                }
            }
        }
    }
}
