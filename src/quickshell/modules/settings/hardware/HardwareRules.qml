pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import qs.services
import qs.modules.shared
import qs.modules.shared.primitives.common
import qs.modules.shared.widgets
import ".."

SettingsPage {
    id: root
    property string deleteId: ""
    property string sourceId: ""
    property string sourceName: ""
    signal returnToDevice(string identity)
    baseWidth: Math.max(0, width - 24)
    function invalidatePreview() { Hardware.preview = null; }
    function edit(rule, keepSource = false) {
        if (!keepSource) { sourceId = ""; sourceName = ""; }
        Hardware.preview = null;
        ruleId.text = rule.id;
        label.text = rule.label || "";
        subsystem.text = rule.subsystem;
        kernel.text = rule.kernel;
        vendor.text = rule.vendor;
        product.text = rule.product;
        uaccess.checked = rule.uaccess;
        mode.currentIndex = ["", "0600", "0660"].indexOf(rule.mode || "");
        group.text = rule.group || "";
        draftEnabled.checked = rule.enabled;

    }
    function prepare() {
        const d = Hardware.detail;
        if (!d?.ruleSupported) return;
        sourceId = d.id;
        sourceName = Hardware.selectedEntity?.name || d.kernel;
        edit({id: "", label: "", subsystem: d.subsystem, kernel: d.kernel,
            vendor: d.usbSelector.vendor, product: d.usbSelector.product,
            uaccess: true, enabled: true, mode: "", group: ""}, true);
        // Class-scoped suffix avoids depending on a changing hidraw/event number.
        if (d.subsystem === "hidraw") kernel.text = "hidraw*";
        else if (d.subsystem === "input" && /^event[0-9]+$/.test(d.kernel)) kernel.text = "event*";
        else if (d.subsystem === "tty") kernel.text = d.kernel.replace(/[0-9]+$/, "*");
    }
    function rule() {
        return {id: ruleId.text, label: label.text, subsystem: subsystem.text, kernel: kernel.text,
            vendor: vendor.text, product: product.text, uaccess: uaccess.checked,
            mode: ["", "0600", "0660"][mode.currentIndex] || "", group: group.text, enabled: draftEnabled.checked};
    }

    component Info: StyledText { Layout.fillWidth: true; wrapMode: Text.Wrap; textFormat: Text.PlainText }
    component LabeledSwitch: RowLayout {
        id: switchRow
        property string text
        property alias checked: control.checked
        Layout.fillWidth: true
        StyledSwitch { id: control; Accessible.name: switchRow.text }
        Info { text: switchRow.text }
    }
    SettingsSection {
        visible: root.sourceId !== ""
        title: Translation.tr("Source device")
        Info { text: root.sourceName; }
        RippleButtonWithIcon {
            objectName: "hardware-return-source"
            mainText: Translation.tr("Return to device")
            materialIcon: "arrow_back"
            onClicked: root.returnToDevice(root.sourceId)
        }
    }
    SettingsSection {
        title: Translation.tr("Own udev rule drafts")
        icon: "rule"
        Info { text: Translation.tr("Privileged installation pending. These drafts never change host permissions. No installer or Polkit helper is packaged in V1. Enabled means included in your draft plan, not active on the host. Only 70-endless-impulse-*.rules filenames are generated. External rules are never imported or modified.") }
        Info { text: Translation.tr("Rules can overlap with other programs. Matching vendor/product grants access to every matching unit and interface class, not one serial number. uaccess grants access to the active local session; browser WebHID site permissions remain separate. Kernel node numbers can change after reconnecting.") }
        RippleButtonWithIcon { mainText: Translation.tr("Reload drafts"); materialIcon: "refresh"; enabled: !Hardware.busy; onClicked: Hardware.loadDrafts() }
        Repeater {
            model: Hardware.drafts
            delegate: ColumnLayout {
                id: draftRow
                required property var modelData
                Layout.fillWidth: true
                Info { text: draftRow.modelData.filename + " · " + (draftRow.modelData.rule.enabled ? Translation.tr("Enabled draft") : Translation.tr("Disabled draft")) + " · " + Translation.tr("Not installed") }
                Flow {
                    Layout.fillWidth: true
                    spacing: 8
                    RippleButtonWithIcon { mainText: Translation.tr("Edit / preview"); materialIcon: "edit"; enabled: !Hardware.busy; onClicked: root.edit(draftRow.modelData.rule) }
                    RippleButtonWithIcon { mainText: draftRow.modelData.rule.enabled ? Translation.tr("Disable draft") : Translation.tr("Enable draft"); materialIcon: "toggle_on"; enabled: !Hardware.busy; onClicked: Hardware.setDraftEnabled(draftRow.modelData.rule, !draftRow.modelData.rule.enabled) }
                    RippleButtonWithIcon {
                        mainText: root.deleteId === draftRow.modelData.rule.id ? Translation.tr("Confirm delete draft") : Translation.tr("Delete")
                        materialIcon: "delete"
                        enabled: !Hardware.busy
                        onClicked: {
                            if (root.deleteId === draftRow.modelData.rule.id) { Hardware.removeDraft(root.deleteId); root.deleteId = ""; }
                            else root.deleteId = draftRow.modelData.rule.id;
                        }
                    }
                }
            }
        }
        Info { visible: !Hardware.drafts.length; text: Translation.tr("No own drafts. Select a supported USB interface in Devices to prepare a rule.") }
        RippleButtonWithIcon { mainText: Translation.tr("Restore previous draft collection"); materialIcon: "undo"; enabled: !Hardware.busy; onClicked: Hardware.restoreDrafts() }
    }
    SettingsSection {
        visible: subsystem.text !== ""
        title: Translation.tr("Assisted rule editor")
        icon: "edit"
        Info { text: Translation.tr("Use a lowercase identifier (1–48 letters, digits or hyphens). IDs and subsystem come from the selected device. Changing an existing identifier creates a separate draft. Empty mode/group leaves that action unspecified; modes are restricted to 0600 or 0660.") }
        MaterialTextField { id: ruleId; objectName: "hardware-rule-ruleId"; Layout.fillWidth: true; wrapMode: TextInput.NoWrap; placeholderText: Translation.tr("Draft identifier"); maximumLength: 48; onTextChanged: root.invalidatePreview() }
        MaterialTextField { id: label; objectName: "hardware-rule-label"; Layout.fillWidth: true; wrapMode: TextInput.NoWrap; placeholderText: Translation.tr("Description"); maximumLength: 120; onTextChanged: root.invalidatePreview() }
        MaterialTextField { id: subsystem; objectName: "hardware-rule-subsystem"; Layout.fillWidth: true; wrapMode: TextInput.NoWrap; readOnly: true; placeholderText: "SUBSYSTEM"; onTextChanged: root.invalidatePreview() }
        MaterialTextField { id: vendor; objectName: "hardware-rule-vendor"; Layout.fillWidth: true; wrapMode: TextInput.NoWrap; readOnly: true; placeholderText: "idVendor"; onTextChanged: root.invalidatePreview() }
        MaterialTextField { id: product; objectName: "hardware-rule-product"; Layout.fillWidth: true; wrapMode: TextInput.NoWrap; readOnly: true; placeholderText: "idProduct"; onTextChanged: root.invalidatePreview() }
        MaterialTextField { id: kernel; objectName: "hardware-rule-kernel"; Layout.fillWidth: true; wrapMode: TextInput.NoWrap; placeholderText: "KERNEL"; maximumLength: 80; onTextChanged: root.invalidatePreview() }
        LabeledSwitch { id: uaccess; text: "TAG+=uaccess"; onCheckedChanged: root.invalidatePreview() }
        StyledComboBox { id: mode; Layout.fillWidth: true; model: [Translation.tr("MODE: unspecified"), "0600", "0660"]; onCurrentIndexChanged: root.invalidatePreview() }
        MaterialTextField { id: group; objectName: "hardware-rule-group"; Layout.fillWidth: true; wrapMode: TextInput.NoWrap; placeholderText: Translation.tr("GROUP: existing group, or empty"); maximumLength: 32; onTextChanged: root.invalidatePreview() }
        LabeledSwitch { id: draftEnabled; text: Translation.tr("Enable in draft plan"); onCheckedChanged: root.invalidatePreview() }
        RippleButtonWithIcon {
            objectName: "hardware-rule-preview"
            mainText: Translation.tr("Validate and preview")
            materialIcon: "preview"
            enabled: !Hardware.busy
            onClicked: Hardware.validateRule(root.rule())
        }
        Info { visible: !!Hardware.preview; text: (Hardware.preview?.filename || "") + "\n" + (Hardware.preview?.content || "") }
        Info { visible: !!Hardware.preview; text: Translation.tr("Review the exact content above. Saving updates only your per-user metadata, preserves the previous collection and checks the saved data. It does not install a rules file or reload udev.") }
        RippleButtonWithIcon {
            visible: !!Hardware.preview
            objectName: "hardware-rule-save"
            mainText: Translation.tr("Confirm and save draft only")
            materialIcon: "save"
            enabled: !Hardware.busy
            onClicked: Hardware.savePreview()
        }
    }
}
