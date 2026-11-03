import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Wayland
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets

PanelWindow {
    visible: DesktopSettings.transaction !== null && !DesktopSettings.resolvingTransaction
    implicitWidth: Math.max(240, Math.min(520, screen.width - 32))
    implicitHeight: content.implicitHeight + 40
    exclusiveZone: 0
    color: "transparent"
    WlrLayershell.namespace: "quickshell:settings-preview"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.OnDemand

    Rectangle {
        anchors.fill: parent
        radius: Appearance.rounding.large
        color: Appearance.m3colors.m3surfaceContainerHigh
        border.width: 2
        border.color: Appearance.colors.colPrimary
    }
    ColumnLayout {
        id: content
        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 20 }
        spacing: 16
        StyledText {
            Layout.fillWidth: true
            text: DesktopSettings.restorationFailed ? Translation.tr("Restoration needs attention") : Translation.tr("Keep these settings?")
            font.pixelSize: Appearance.font.pixelSize.larger
            font.weight: Font.DemiBold
            wrapMode: Text.WordWrap
        }
        StyledText {
            Layout.fillWidth: true
            text: DesktopSettings.restorationFailed
                ? Translation.tr("Automatic restoration stopped after an error. Retry restoring the previous settings.")
                : Translation.tr("Previous settings will be restored in %1 seconds unless you confirm.").arg(DesktopSettings.remaining)
            wrapMode: Text.WordWrap
        }
        RowLayout {
            Layout.fillWidth: true
            RippleButtonWithIcon {
                Layout.fillWidth: true
                materialIcon: "undo"
                mainText: DesktopSettings.restorationFailed ? Translation.tr("Retry restoration") : Translation.tr("Revert")
                enabled: !DesktopSettings.resolvingTransaction
                onClicked: DesktopSettings.revert()
            }
            RippleButtonWithIcon {
                Layout.fillWidth: true
                materialIcon: "check"
                mainText: Translation.tr("Keep changes")
                enabled: !DesktopSettings.resolvingTransaction && !DesktopSettings.restorationFailed && DesktopSettings.remaining > 0
                onClicked: DesktopSettings.keep()
            }
        }
    }
}
