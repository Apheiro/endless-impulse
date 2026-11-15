pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import qs.services
import qs.modules.shared.widgets

SettingsPage {
    Component.onCompleted: { if (!DesktopSettings.loaded) DesktopSettings.refresh(); }
    Repeater {
        model: ["Layout", "Borders", "Opacity", "Blur", "Shadows", "Animations"]
        delegate: SettingsSection {
            required property string modelData
            property string section: modelData
            title: Translation.tr(section)
            icon: section === "Layout" ? "grid_view" : section === "Animations" ? "animation" : "rounded_corner"
            enabled: DesktopSettings.loaded && !DesktopSettings.busy && !DesktopSettings.transaction
            Repeater {
                model: DesktopSettings.fields.filter(field => field.section === section)
                delegate: DesktopSettingField {
                    required property var modelData
                    field: modelData
                    value: DesktopSettings.option(field.key)
                    enabled: DesktopSettings.supported[field.key] ?? false
                    onEdited: value => DesktopSettings.put("options", field.key, value)
                }
            }
        }
    }
    SettingsSection {
        visible: Object.keys(DesktopSettings.saved.options).length > 0
        title: Translation.tr("Restore inherited settings")
        icon: "settings_backup_restore"
        StyledText {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            text: Translation.tr("Remove Endless Impulse's saved window overrides and use your original Hyprland configuration. This also uses the preview and confirmation step.")
        }
        RippleButtonWithIcon {
            materialIcon: "restore"
            mainText: Translation.tr("Reset window overrides")
            enabled: !DesktopSettings.busy && !DesktopSettings.transaction
            onClicked: {
                for (const key of Object.keys(DesktopSettings.saved.options)) {
                    const field = DesktopSettings.fields.find(field => field.key === key);
                    if (["Layout", "Borders", "Opacity", "Blur", "Shadows", "Animations"].includes(field?.section)) DesktopSettings.put("options", key, null);
                }
            }
        }
    }
}
