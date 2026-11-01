pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Window
import QtQuick.Controls as Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets
import "../shared/functions/GradientColors.js" as GradientColors

ColumnLayout {
    id: root
    required property string value
    signal edited(string nextValue)
    readonly property var parsed: GradientColors.parse(value)
    property int selectedStop: 0
    property bool manual: false
    property alias picker: picker
    Layout.fillWidth: true
    spacing: 8

    function pick(index) {
        if (!parsed.valid) return;
        selectedStop = index;
        picker.selectedColor = GradientColors.qtColor(parsed.colors[index]);
        picker.open();
    }
    function updateColor(index, color) {
        if (index < 0 || index >= parsed.colors.length) return;
        const next = [...parsed.colors];
        next[index] = GradientColors.fromColor(color);
        edited(GradientColors.format(next, parsed.angle, parsed.hasAngle));
    }
    function addColor() {
        if (!parsed.valid || parsed.colors.length >= 10) return;
        edited(GradientColors.format([...parsed.colors, parsed.colors[parsed.colors.length - 1]], parsed.angle, true));
    }
    function removeColor(index) {
        if (parsed.colors.length <= 1) return;
        const next = parsed.colors.filter((_, i) => i !== index);
        edited(GradientColors.format(next, parsed.angle, next.length > 1));
    }
    ColorDialog {
        id: picker
        title: Translation.tr("Choose color and opacity")
        parentWindow: root.Window.window
        popupType: Controls.Popup.Item
        options: ColorDialog.ShowAlphaChannel | ColorDialog.DontUseNativeDialog | ColorDialog.NoEyeDropperButton
        onAccepted: root.updateColor(root.selectedStop, selectedColor)
    }
    Canvas {
        id: preview
        Layout.fillWidth: true
        Layout.preferredHeight: 40
        visible: root.parsed.valid
        property var stops: root.parsed.colors
        property real angle: root.parsed.angle
        property color checkA: Appearance.colors.colLayer0Base
        property color checkB: Appearance.colors.colLayer3Base
        onStopsChanged: requestPaint()
        onAngleChanged: requestPaint()
        onCheckAChanged: requestPaint()
        onCheckBChanged: requestPaint()
        onWidthChanged: requestPaint()
        onPaint: {
            const ctx = getContext("2d");
            ctx.reset();
            const radius = Math.min(Appearance.rounding.small, height / 2);
            ctx.beginPath();
            ctx.moveTo(radius, 0); ctx.lineTo(width-radius, 0); ctx.quadraticCurveTo(width, 0, width, radius);
            ctx.lineTo(width, height-radius); ctx.quadraticCurveTo(width, height, width-radius, height);
            ctx.lineTo(radius, height); ctx.quadraticCurveTo(0, height, 0, height-radius);
            ctx.lineTo(0, radius); ctx.quadraticCurveTo(0, 0, radius, 0); ctx.closePath(); ctx.clip();
            for (let y=0; y<height; y+=8) for (let x=0; x<width; x+=8) {
                ctx.fillStyle = (Math.floor(x/8)+Math.floor(y/8))%2 ? checkA : checkB;
                ctx.fillRect(x,y,8,8);
            }
            if (!stops.length) return;
            const radians = angle * Math.PI / 180;
            const length = Math.abs(width*Math.cos(radians)) + Math.abs(height*Math.sin(radians));
            const dx = Math.cos(radians)*length/2, dy = Math.sin(radians)*length/2;
            const gradient = ctx.createLinearGradient(width/2-dx,height/2-dy,width/2+dx,height/2+dy);
            for (let i=0; i<stops.length; i++) gradient.addColorStop(stops.length===1 ? 0 : i/(stops.length-1), Qt.color(GradientColors.qtColor(stops[i])));
            ctx.fillStyle=gradient; ctx.fillRect(0,0,width,height);
        }
    }
    Flow {
        Layout.fillWidth: true
        spacing: 6
        Repeater {
            model: root.parsed.colors
            delegate: RowLayout {
                id: stop
                required property string modelData
                required property int index
                spacing: 0
                RippleButton {
                    implicitWidth: 108
                    implicitHeight: 36
                    onClicked: root.pick(stop.index)
                    contentItem: RowLayout {
                        spacing: 6
                        Rectangle {
                            implicitWidth: 22; implicitHeight: 22
                            radius: Appearance.rounding.unsharpen
                            color: GradientColors.qtColor(stop.modelData)
                            border.width: 1; border.color: Appearance.colors.colOutlineVariant
                        }
                        StyledText { text: "#" + stop.modelData.toUpperCase(); font.pixelSize: Appearance.font.pixelSize.smaller }
                    }
                    StyledToolTip { text: Translation.tr("Choose color and opacity") }
                }
                RippleButton {
                    visible: root.parsed.colors.length > 1
                    implicitWidth: 24; implicitHeight: 30
                    onClicked: root.removeColor(stop.index)
                    contentItem: MaterialSymbol { text: "close"; iconSize: 14 }
                    StyledToolTip { text: Translation.tr("Remove color") }
                }
            }
        }
        RippleButtonWithIcon {
            visible: root.parsed.valid && root.parsed.colors.length < 10
            materialIcon: "add"
            mainText: Translation.tr("Add color")
            onClicked: root.addColor()
        }
    }
    SettingsRange {
        visible: root.parsed.valid && (root.parsed.colors.length > 1 || root.parsed.hasAngle)
        text: Translation.tr("Gradient angle")
        from: 0; to: 360; decimals: 0; stepSize: 1; suffix: "°"
        value: root.parsed.angle
        onEdited: value => root.edited(GradientColors.format(root.parsed.colors, value, true))
    }
    RippleButtonWithIcon {
        materialIcon: root.manual ? "expand_less" : "code"
        mainText: Translation.tr("Edit RGBA values")
        onClicked: root.manual = !root.manual
    }
    MaterialTextField {
        Layout.fillWidth: true
        visible: root.manual || !root.parsed.valid
        text: root.value
        placeholderText: "rgba(RRGGBBAA) rgba(RRGGBBAA) 90deg"
        selectByMouse: true
        onEditingFinished: { if (text !== root.value) root.edited(text); }
    }
}
