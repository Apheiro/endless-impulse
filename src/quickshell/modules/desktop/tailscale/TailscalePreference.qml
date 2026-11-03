pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import Quickshell
import qs.services
import qs.modules.shared
import qs.modules.shared.primitives.common
import qs.modules.shared.widgets
ColumnLayout {
    id: root
    required property string preferenceKey
    property string label: preferenceKey
    property string description: ""
    property string icon: "tune"
    readonly property var value: TailscaleControl.state.prefs[preferenceKey]
    visible: TailscaleControl.state.setFlags?.includes(preferenceKey) ?? false
    Layout.fillWidth: true
    spacing: 8
    RowLayout {
        Layout.fillWidth: true; spacing: 10
        MaterialSymbol { text: root.icon; iconSize: 21; color: Appearance.colors.colSubtext }
        ColumnLayout {
            Layout.fillWidth: true; spacing: 2
            StyledText { Layout.fillWidth: true; text: root.label; textFormat: Text.PlainText; wrapMode: Text.WordWrap; font.weight: Font.Medium }
            StyledText { Layout.fillWidth: true; visible: !!root.description; text: root.description; textFormat: Text.PlainText; wrapMode: Text.WordWrap; color: Appearance.colors.colSubtext; font.pixelSize: Appearance.font.pixelSize.smaller }
        }
        StyledSwitch { visible: typeof root.value === "boolean"; checked: root.value === true; enabled: !TailscaleControl.busy; onToggled: TailscaleControl.setFlag(root.preferenceKey, checked) }
    }
    RowLayout {
        visible: typeof root.value === "string"; Layout.fillWidth: true
        MaterialTextField { id: field; Layout.fillWidth: true; text: String(root.value ?? ""); wrapMode: TextInput.NoWrap; placeholderText: root.preferenceKey === "advertise-routes" ? "10.0.0.0/24,192.168.0.0/24" : root.label }
        RippleButtonWithIcon { materialIcon: "check"; mainText: Translation.tr("Apply"); enabled: !TailscaleControl.busy && field.text !== root.value; onClicked: TailscaleControl.setFlag(root.preferenceKey, field.text) }
    }
}
