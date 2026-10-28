pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import qs.services
import qs.modules.common
import qs.modules.common.widgets

ColumnLayout {
    id: root
    required property var field
    required property var value
    signal edited(var nextValue)
    Layout.fillWidth: true
    spacing: 6

    StyledText {
        Layout.fillWidth: true
        visible: root.field.type !== "bool"
        text: Translation.tr(root.field.label)
        wrapMode: Text.WordWrap
        color: Appearance.m3colors.m3onSurfaceVariant
    }
    Loader {
        Layout.fillWidth: true
        sourceComponent: root.field.type === "bool" ? switchControl
            : root.field.type === "enum" ? choiceControl
            : root.field.type === "int" ? integerControl : textControl
    }
    Component {
        id: switchControl
        RowLayout {
            StyledText {
                Layout.fillWidth: true
                text: Translation.tr(root.field.label)
                wrapMode: Text.WordWrap
            }
            StyledSwitch {
                Layout.fillWidth: false
                checked: !!root.value
                onClicked: root.edited(checked)
            }
        }
    }
    Component {
        id: choiceControl
        StyledComboBox {
            model: root.field.choices.map(value => ({label: value === "" ? Translation.tr("System default") : value, value: value}))
            textRole: "label"
            currentIndex: Math.max(0, root.field.choices.indexOf(root.value))
            onActivated: index => root.edited(root.field.choices[index])
        }
    }
    Component {
        id: integerControl
        Item {
            implicitHeight: 40
            SpinBox {
                id: spin
                width: Math.min(parent.width, 260)
                height: parent.height
                from: root.field.minimum
                to: root.field.maximum
                value: Number(root.value ?? root.field.default)
                editable: true
                palette.text: Appearance.colors.colOnLayer0
                palette.buttonText: Appearance.colors.colOnLayer0
                background: Rectangle { color: Appearance.colors.colLayer2; radius: Appearance.rounding.small }
                up.indicator: Rectangle {
                    x: spin.width - width
                    width: 40; height: spin.height
                    radius: Appearance.rounding.small
                    color: spin.up.pressed ? Appearance.colors.colLayer2Active : Appearance.colors.colLayer2
                    MaterialSymbol { anchors.centerIn: parent; text: "add"; iconSize: 20 }
                }
                down.indicator: Rectangle {
                    width: 40; height: spin.height
                    radius: Appearance.rounding.small
                    color: spin.down.pressed ? Appearance.colors.colLayer2Active : Appearance.colors.colLayer2
                    MaterialSymbol { anchors.centerIn: parent; text: "remove"; iconSize: 20 }
                }
                onValueModified: root.edited(value)
            }
        }
    }
    Component {
        id: textControl
        MaterialTextField {
            text: String(root.value ?? root.field.default ?? "")
            selectByMouse: true
            wrapMode: TextInput.NoWrap
            placeholderText: root.field.type === "float" ? root.field.minimum + " – " + root.field.maximum
                : root.field.type === "gradient" ? "rgba(RRGGBBAA) · rgb(RRGGBB)" : ""
            onEditingFinished: {
                const next = root.field.type === "float" ? Number(text) : text;
                if (root.field.type === "float" && (!text.trim() || !Number.isFinite(next))) {
                    DesktopSettings.failed = true;
                    DesktopSettings.message = "Enter a valid number for " + root.field.label;
                    return;
                }
                if (next !== root.value) root.edited(next);
            }
        }
    }
}
