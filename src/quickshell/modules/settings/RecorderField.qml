pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets

ColumnLayout {
    id: root
    required property var field
    required property var value
    signal edited(var nextValue)
    Layout.fillWidth: true
    spacing: 4
    enabled: field.supported
    readonly property var choices: {
        if (field.key === "codec" && ScreenRecorder.capabilities.codecs.length)
            return field.choices.filter(choice => choice === "auto" || ScreenRecorder.capabilities.codecs.includes(choice) || choice === value);
        return field.choices;
    }
    StyledText { Layout.fillWidth: true; visible: root.field.type !== "int"; text: Translation.tr(root.field.label); wrapMode: Text.WordWrap; font.pixelSize: Appearance.font.pixelSize.small }
    Loader {
        Layout.fillWidth: root.field.type !== "bool"
        Layout.alignment: Qt.AlignLeft
        sourceComponent: root.field.type === "bool" ? boolField : root.field.type === "int" ? integerField : root.field.type === "enum" ? enumField : root.field.type === "lines" ? linesField : textField
    }
    Component {
        id: integerField
        DesktopSettingField {
            controlName: "recorder-value-" + root.field.key
            field: root.field
            value: root.value
            onEdited: value => root.edited(value)
        }
    }
    Component { id: boolField; StyledSwitch { objectName: "recorder-value-" + root.field.key; checked: !!root.value; onClicked: root.edited(checked) } }
    Component {
        id: enumField
        StyledComboBox {
            model: root.choices.map(value => ({name: value === "" ? Translation.tr("Automatic") : value}))
            textRole: "name"
            currentIndex: root.choices.indexOf(root.value)
            onActivated: index => root.edited(root.choices[index])
        }
    }
    Component {
        id: textField
        MaterialTextField {
            objectName: "recorder-value-" + root.field.key
            text: String(root.value ?? "")
            selectByMouse: true
            echoMode: root.field.type === "password" ? TextInput.Password : TextInput.Normal
            onTextEdited: root.edited(root.field.type === "int" ? Number(text) : text)
        }
    }
    Component {
        id: linesField
        MaterialTextArea {
            id: linesEditor
            Component.onCompleted: text = (root.value || []).join("\n")
            Connections {
                target: root
                function onValueChanged() { if (!linesEditor.activeFocus) linesEditor.text = (root.value || []).join("\n"); }
            }
            wrapMode: TextEdit.Wrap
            onTextChanged: { if (activeFocus) root.edited(text.split("\n").map(value => value.trim()).filter(Boolean)); }
        }
    }
    StyledText {
        Layout.fillWidth: true
        visible: text.length > 0
        text: !root.field.supported ? Translation.tr("Unavailable in the installed GPU Screen Recorder version") : Translation.tr(root.field.hint)
        wrapMode: Text.WordWrap
        color: Appearance.colors.colSubtext
        font.pixelSize: Appearance.font.pixelSize.smaller
    }
}
