import qs.modules.shared
import QtQuick
import QtQuick.Controls.Material
import QtQuick.Controls

/**
 * Theme-controlled outlined TextField, independent of the Controls backend.
 * https://m3.material.io/components/text-fields/overview
 * Note: We don't use NativeRendering because it makes the small placeholder text look weird
 */
TextField {
    id: root
    Material.theme: Appearance.m3colors.darkmode ? Material.Dark : Material.Light
    Material.accent: Appearance.m3colors.m3primary
    Material.primary: Appearance.m3colors.m3primary
    Material.background: Appearance.m3colors.m3surface
    Material.foreground: Appearance.m3colors.m3onSurface
    Material.containerStyle: Material.Outlined
    renderType: Text.QtRendering
    leftPadding: Appearance.sizes.textInputHorizontalPadding
    rightPadding: Appearance.sizes.textInputHorizontalPadding
    topPadding: Appearance.sizes.textInputVerticalPadding + topInset
    bottomPadding: Appearance.sizes.textInputVerticalPadding
    // The shell uses Controls Basic. Material attached properties alone do not
    // theme its default frame, so own the surface and outline explicitly.
    color: Appearance.colors.colOnLayer1
    background: Rectangle {
        implicitHeight: Appearance.sizes.textInputMinimumHeight
        radius: Appearance.rounding.unsharpenmore
        color: Appearance.colors.colLayer1
        border.width: root.activeFocus ? 2 : 1
        border.color: !root.enabled ? Appearance.colors.colLayer0Border
            : root.activeFocus ? Appearance.colors.colPrimary
            : root.hovered ? Appearance.colors.colOutline : Appearance.colors.colLayer0Border
        opacity: root.enabled ? 1 : .4
        Behavior on border.color {
            animation: Appearance.animation.elementMoveFast.colorAnimation.createObject(this)
        }
    }

    selectedTextColor: Appearance.m3colors.m3onSecondaryContainer
    selectionColor: Appearance.colors.colSecondaryContainer
    placeholderTextColor: Appearance.m3colors.m3outline
    clip: true

    font {
        family: Appearance.font.family.main
        pixelSize: Appearance?.font.pixelSize.small ?? 15
        hintingPreference: Font.PreferFullHinting
        variableAxes: Appearance.font.variableAxes.main
    }
    wrapMode: TextEdit.Wrap

    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.NoButton
        hoverEnabled: true
        cursorShape: Qt.IBeamCursor
    }
}
