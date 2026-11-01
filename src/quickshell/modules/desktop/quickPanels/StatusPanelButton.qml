import qs.modules.shared.primitives.common
import QtQuick
import qs
import Quickshell
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets

RippleButton {
    id: root
    required property string section
    required property string materialIcon
    property string glyphName: "status-button-glyph"
    property color foreground: toggled || GlobalStates.sidebarRightOpen ? Appearance.colors.colOnSecondaryContainer : Appearance.colors.colOnLayer0
    readonly property var controller: section === "audio" ? AudioControl : section === "network" ? NetworkControl : BluetoothManager
    implicitWidth: Appearance.sizes.statusIconWidth
    implicitHeight: Appearance.sizes.statusIconHeight
    padding: 0
    toggled: controller.opened
    buttonRadius: Appearance.rounding.full
    colBackground: "transparent"
    colBackgroundToggled: Appearance.colors.colSecondaryContainer
    colBackgroundToggledHover: Appearance.colors.colSecondaryContainerHover
    Accessible.name: ({audio: Translation.tr("Sound"), network: Translation.tr("Network"), bluetooth: "Bluetooth"})[section]
    Accessible.description: Translation.tr("Left click: sidebar. Right click: quick controls.")
    onClicked: QuickPanelState.toggleSidebar()
    altAction: () => {
        const name = root.QsWindow.window?.screen?.name;
        if (controller.opened && (!name || controller.screenName === name)) controller.close();
        else controller.open(name);
    }
    contentItem: Item {
        MaterialSymbol {
            objectName: root.glyphName
            anchors.centerIn: parent
            text: root.materialIcon
            iconSize: Appearance.font.pixelSize.larger
            fill: 1
            color: root.foreground
        }
    }
}
