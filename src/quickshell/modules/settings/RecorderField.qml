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
    objectName: "recorder-field-" + field.key
    signal edited(var nextValue)
    Layout.fillWidth: true
    Layout.minimumWidth: 0
    spacing: 6
    enabled: field.supported
    readonly property string label: Translation.tr(field.label)
    readonly property var choices: {
        if (field.key === "codec" && ScreenRecorder.capabilities.codecs.length)
            return field.choices.filter(choice => choice === "auto" || ScreenRecorder.capabilities.codecs.includes(choice) || choice === value);
        return field.choices;
    }
    StyledText {
        Layout.fillWidth: true
        visible: !["bool", "int", "float"].includes(root.field.type)
        text: root.label
        wrapMode: Text.WordWrap
        font.pixelSize: Appearance.font.pixelSize.small
    }
    Loader {
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        sourceComponent: root.field.type === "bool" ? boolField
            : ["int", "float"].includes(root.field.type) ? numberField
            : root.field.type === "enum" ? enumField
            : root.field.type === "lines" ? linesField : textField
    }
    Component {
        id: numberField
        ColumnLayout {
            spacing: 4
            DesktopSettingField {
                controlName: "recorder-value-" + root.field.key
                field: root.field
                value: root.value
                onEdited: value => root.edited(value)
            }
            StyledText {
                Layout.fillWidth: true
                text: root.field.minimum + " – " + root.field.maximum
                font.pixelSize: Appearance.font.pixelSize.smaller
                color: Appearance.colors.colSubtext
            }
        }
    }
    Component {
        id: boolField
        RowLayout {
            implicitHeight: Math.max(40, boolLabel.implicitHeight, boolSwitch.implicitHeight)
            StyledText {
                id: boolLabel
                Layout.fillWidth: true
                text: root.label
                wrapMode: Text.WordWrap
                font.pixelSize: Appearance.font.pixelSize.small
            }
            StyledSwitch {
                id: boolSwitch
                objectName: "recorder-value-" + root.field.key
                Accessible.name: root.label
                checked: !!root.value
                onClicked: root.edited(checked)
            }
        }
    }
    Component {
        id: enumField
        StyledComboBox {
            objectName: "recorder-value-" + root.field.key
            Accessible.name: root.label
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
            Accessible.name: root.label
            text: String(root.value ?? "")
            selectByMouse: true
            wrapMode: TextInput.NoWrap
            echoMode: root.field.type === "password" ? TextInput.Password : TextInput.Normal
            onTextEdited: root.edited(text)
        }
    }
    Component {
        id: linesField
        MaterialTextArea {
            id: linesEditor
            objectName: "recorder-value-" + root.field.key
            Accessible.name: root.label
            property bool synchronizing: true
            function lines() { return text.split("\n").map(value => value.trim()).filter(Boolean); }
            function sync() {
                synchronizing = true;
                text = (root.value || []).join("\n");
                synchronizing = false;
            }
            Component.onCompleted: sync()
            Connections {
                target: root
                function onValueChanged() {
                    // Keep the caret/unfinished line during typing, but apply external
                    // changes (Discard or Add track) even while the editor has focus.
                    if (JSON.stringify(linesEditor.lines()) !== JSON.stringify(root.value || [])) linesEditor.sync();
                }
            }
            implicitHeight: Math.max(96, contentHeight + topPadding + bottomPadding)
            selectByMouse: true
            wrapMode: TextEdit.Wrap
            onTextChanged: if (!synchronizing && activeFocus) root.edited(lines())
        }
    }
    StyledText {
        Layout.fillWidth: true
        visible: text.length > 0
        text: !root.field.supported ? Translation.tr("Unavailable in the installed GPU Screen Recorder version") : Translation.tr(root.field.hint)
        wrapMode: Text.WrapAnywhere
        color: Appearance.colors.colSubtext
        font.pixelSize: Appearance.font.pixelSize.smaller
    }
}
