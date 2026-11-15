pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import qs.services
import qs.modules.shared
import qs.modules.shared.primitives.common
import qs.modules.shared.widgets

SettingsPage {
    id: root
    Component.onCompleted: InternalSurfaces.load()

    SettingsSection {
        title: Translation.tr("Internal graphical processes")
        icon: "account_tree"
        StyledText {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            text: Translation.tr("Auxiliary surfaces use a reserved workspace, separate from minimized windows. Rules manage windows, not processes. Disabling or removing a rule restores tracked surfaces to their original workspace.")
        }
        StyledText {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            text: InternalSurfaces.workspace
            color: Appearance.colors.colSubtext
        }
        StyledText {
            visible: InternalSurfaces.error !== ""
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            text: InternalSurfaces.error
            color: Appearance.colors.colError
        }
        RippleButtonWithIcon {
            materialIcon: "refresh"
            mainText: Translation.tr("Refresh / retry")
            enabled: !InternalSurfaces.busy
            onClicked: InternalSurfaces.retry()
        }
    }
    Repeater {
        model: InternalSurfaces.entries
        delegate: SettingsSection {
            id: entryCard
            required property var modelData
            readonly property var surfaces: InternalSurfaces.surfaces(modelData)
            title: modelData.windowClass + (modelData.builtin ? " · " + Translation.tr("Built-in") : "")
            icon: "select_window"
            StyledText {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: entryCard.modelData.purpose
            }
            StyledText {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                color: Appearance.colors.colSubtext
                text: Translation.tr("Exact class") + ": " + entryCard.modelData.windowClass
                    + (entryCard.modelData.builtin ? " · X11" : "\n" + Translation.tr("Exact title") + ": " + entryCard.modelData.title)
                    + "\n" + (entryCard.surfaces.length ? Translation.tr("Active") : Translation.tr("Inactive"))
                    + " · " + Translation.tr("Surfaces") + ": " + entryCard.surfaces.length
            }
            Repeater {
                model: entryCard.surfaces
                delegate: StyledText {
                    required property var modelData
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                    text: "PID " + modelData.pid + " · " + modelData.address + " · " + modelData.workspace.name
                        + (modelData.workspace.name === InternalSurfaces.workspace ? " · " + Translation.tr("Internal") : " · " + Translation.tr("Outside reserved workspace"))
                }
            }
            ColumnLayout {
                Layout.fillWidth: true
                RippleButtonWithIcon {
                    Layout.fillWidth: true
                    materialIcon: entryCard.modelData.enabled ? "pause" : "play_arrow"
                    mainText: entryCard.modelData.enabled ? Translation.tr("Disable and restore") : Translation.tr("Enable")
                    enabled: !InternalSurfaces.busy
                    onClicked: InternalSurfaces.setEnabled(entryCard.modelData, !entryCard.modelData.enabled)
                }
                RippleButtonWithIcon {
                    Layout.fillWidth: true
                    visible: !entryCard.modelData.builtin
                    materialIcon: "delete"
                    mainText: Translation.tr("Remove and restore")
                    enabled: !InternalSurfaces.busy
                    onClicked: InternalSurfaces.remove(entryCard.modelData)
                }
            }
        }
    }
    SettingsSection {
        title: Translation.tr("Add an auxiliary surface rule")
        icon: "add"
        StyledText {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            text: Translation.tr("Use a dedicated auxiliary class and an exact title. Only floating windows match. Wildcards, duplicate rules and critical shell or authentication classes are rejected. Never enter the class and title of an application’s main window.")
        }
        MaterialTextField {
            id: classField
            objectName: "internal-surface-class"
            Layout.fillWidth: true
            placeholderText: Translation.tr("Exact window class (3–128 characters)")
            maximumLength: 128
            wrapMode: TextInput.NoWrap
        }
        MaterialTextField {
            id: titleField
            objectName: "internal-surface-title"
            Layout.fillWidth: true
            placeholderText: Translation.tr("Exact auxiliary window title (required, up to 160 characters)")
            maximumLength: 160
            wrapMode: TextInput.NoWrap
        }
        MaterialTextField {
            id: purposeField
            objectName: "internal-surface-purpose"
            Layout.fillWidth: true
            placeholderText: Translation.tr("Purpose (required, up to 240 characters)")
            maximumLength: 240
            wrapMode: TextInput.NoWrap
        }
        RippleButtonWithIcon {
            objectName: "internal-surface-add"
            materialIcon: "add"
            mainText: Translation.tr("Add rule")
            enabled: !InternalSurfaces.busy && classField.text.trim() !== "" && titleField.text.trim() !== "" && purposeField.text.trim() !== ""
            onClicked: InternalSurfaces.add(classField.text, titleField.text, purposeField.text)
        }
    }
}
