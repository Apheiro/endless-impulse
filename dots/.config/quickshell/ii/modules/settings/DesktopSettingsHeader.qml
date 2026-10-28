import QtQuick
import QtQuick.Layouts
import qs.services
import qs.modules.common
import qs.modules.common.widgets

SettingsSection {
    title: Translation.tr("Apply changes")
    icon: "tune"
    StyledText {
        Layout.fillWidth: true
        wrapMode: Text.WordWrap
        text: DesktopSettings.transaction
            ? Translation.tr("Keep these settings? Automatic restore in %1 seconds.").arg(DesktopSettings.remaining)
            : Translation.tr("Edit a draft, then test it for 20 seconds. Nothing changes until you click Test changes. Close Settings without confirming and the previous configuration will be restored.")
    }
    StyledText {
        Layout.fillWidth: true
        visible: DesktopSettings.message !== ""
        text: Translation.tr(DesktopSettings.message)
        wrapMode: Text.WordWrap
        color: DesktopSettings.failed ? Appearance.m3colors.m3error : Appearance.m3colors.m3onSurfaceVariant
    }
    Flow {
        Layout.fillWidth: true
        spacing: 8
        RippleButtonWithIcon {
            visible: !DesktopSettings.integrated && DesktopSettings.loaded
            enabled: !DesktopSettings.busy
            materialIcon: "link"
            mainText: Translation.tr("Enable desktop integration")
            onClicked: DesktopSettings.request("install")
        }
        RippleButtonWithIcon {
            visible: !DesktopSettings.transaction
            enabled: DesktopSettings.integrated && DesktopSettings.changes > 0 && !DesktopSettings.busy
            materialIcon: "play_arrow"
            mainText: Translation.tr("Test changes") + " (" + DesktopSettings.changes + ")"
            onClicked: DesktopSettings.preview()
        }
        RippleButtonWithIcon {
            visible: !!DesktopSettings.transaction
            enabled: !DesktopSettings.busy && DesktopSettings.remaining > 0
            materialIcon: "check"
            mainText: Translation.tr("Keep changes")
            onClicked: DesktopSettings.keep()
        }
        RippleButtonWithIcon {
            visible: !!DesktopSettings.transaction
            enabled: !DesktopSettings.busy
            materialIcon: "undo"
            mainText: Translation.tr("Revert now")
            onClicked: DesktopSettings.revert()
        }
        RippleButtonWithIcon {
            visible: !DesktopSettings.transaction
            enabled: !DesktopSettings.busy && DesktopSettings.changes > 0
            materialIcon: "edit_off"
            mainText: Translation.tr("Discard draft")
            onClicked: DesktopSettings.discard()
        }
        RippleButtonWithIcon {
            visible: !DesktopSettings.transaction
            enabled: !DesktopSettings.busy && !DesktopSettings.changes
            materialIcon: "refresh"
            mainText: DesktopSettings.busy ? Translation.tr("Loading…") : Translation.tr("Refresh")
            onClicked: DesktopSettings.refresh()
        }
    }
}
