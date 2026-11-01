pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import qs.services
import qs.modules.shared.widgets

SettingsPage {
    id: root
    property int selectedDevice: 0
    readonly property var device: DesktopSettings.devices[selectedDevice] ?? null
    Component.onCompleted: { if (!DesktopSettings.loaded) DesktopSettings.refresh(); }
    Repeater {
        model: ["Keyboard", "Pointer", "Touchpad"]
        delegate: SettingsSection {
            required property string modelData
            property string section: modelData
            title: Translation.tr(section)
            icon: section === "Keyboard" ? "keyboard" : "mouse"
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
        title: Translation.tr("Per-device overrides")
        icon: "devices"
        visible: DesktopSettings.devices.length > 0
        enabled: DesktopSettings.loaded && !DesktopSettings.busy && !DesktopSettings.transaction
        StyledText {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            text: Translation.tr("Override individual devices here. Unchanged fields are left to Hyprland; displayed defaults come from the global settings. Existing custom device rules remain in your configuration.")
        }
        StyledComboBox {
            model: DesktopSettings.devices.map(device => ({label: device.name + " · " + device.kind}))
            textRole: "label"
            currentIndex: root.selectedDevice
            onActivated: index => root.selectedDevice = index
        }
        Repeater {
            model: root.device ? DesktopSettings.deviceFields(root.device.kind) : []
            delegate: DesktopSettingField {
                required property var modelData
                field: modelData
                value: DesktopSettings.deviceValue(root.device.name, field)
                onEdited: value => DesktopSettings.putDevice(root.device.name, field.key, value)
            }
        }
        RippleButtonWithIcon {
            materialIcon: "restore"
            mainText: Translation.tr("Remove saved overrides for this device")
            enabled: !!root.device && Object.prototype.hasOwnProperty.call(DesktopSettings.saved.devices, root.device.name)
            onClicked: DesktopSettings.put("devices", root.device.name, null)
        }
    }
    SettingsSection {
        title: Translation.tr("Restore inherited input settings")
        icon: "restore"
        RippleButtonWithIcon {
            mainText: Translation.tr("Reset global input overrides")
            materialIcon: "settings_backup_restore"
            enabled: !DesktopSettings.busy && !DesktopSettings.transaction
            onClicked: {
                for (const key of Object.keys(DesktopSettings.saved.options)) {
                    if (key.startsWith("input:")) DesktopSettings.put("options", key, null);
                }
            }
        }
    }
}
