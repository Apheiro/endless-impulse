pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets

ColumnLayout {
    id: root
    property string text: ""
    property string icon: ""
    property real value: 0
    property real from: 0
    property real to: 1
    property real stepSize: 0.01
    property int decimals: 2
    property var stopIndicatorValues: [root.to]
    property string suffix: ""
    property bool invalid: false
    signal edited(real nextValue)
    Layout.fillWidth: true
    Layout.minimumWidth: 0
    spacing: 6

    function format(number) { return Number(number).toFixed(decimals); }
    function submit(text, finalEdit) {
        const number = Number(text.replace(",", "."));
        const valid = !!text.trim() && Number.isFinite(number) && number >= from && number <= to;
        invalid = !!finalEdit && !valid;
        if (valid && number !== value) edited(number);
    }
    RowLayout {
        Layout.fillWidth: true
        visible: root.text.length > 0
        OptionalMaterialSymbol { visible: root.icon.length > 0; icon: root.icon }
        StyledText { Layout.fillWidth: true; text: root.text; wrapMode: Text.WordWrap }
    }
    RowLayout {
        Layout.fillWidth: true
        spacing: 12
        StyledSlider {
            objectName: "settings-range-slider"
            Layout.fillWidth: true
            Layout.minimumWidth: 40
            from: root.from
            to: root.to
            stepSize: root.stepSize
            snapMode: Slider.SnapAlways
            value: root.value
            usePercentTooltip: false
            tooltipContent: root.format(value) + root.suffix
            stopIndicatorValues: root.stopIndicatorValues
            onMoved: { root.invalid = false; root.edited(Number(value.toFixed(root.decimals))); }
        }
        MaterialTextField {
            id: valueField
            property bool userEdit: false
            objectName: "settings-range-value"
            Layout.preferredWidth: 84
            Layout.maximumWidth: 100
            Component.onCompleted: text = root.format(root.value)
            Connections {
                target: root
                function onValueChanged() { root.invalid = false; if (!valueField.userEdit) valueField.text = root.format(root.value); }
            }
            selectByMouse: true
            inputMethodHints: Qt.ImhFormattedNumbersOnly
            onTextEdited: { userEdit = true; root.submit(text, false); userEdit = false; }
            onEditingFinished: { root.submit(text, true); if (!root.invalid) text = root.format(root.value); }
        }
        StyledText { visible: root.suffix.length > 0; text: root.suffix; color: Appearance.colors.colSubtext }
    }
    StyledText {
        visible: root.invalid
        Layout.fillWidth: true
        text: Translation.tr("Enter a value between %1 and %2").arg(root.format(root.from)).arg(root.format(root.to))
        color: Appearance.m3colors.m3error
        font.pixelSize: Appearance.font.pixelSize.smaller
        wrapMode: Text.WordWrap
    }
}
