import QtQuick
import qs.modules.shared

// A content surface placed over the Settings window's colLayer0 base.
Rectangle {
    enum Tone { Surface, Primary, Secondary }

    property bool emphasized: false
    property int tone: SettingsCard.Surface
    property real surfaceOpacity: 1
    readonly property color baseSurfaceColor: Appearance.colors.colBackgroundSurfaceContainer
    readonly property color foregroundColor: tone === SettingsCard.Primary
        ? Appearance.colors.colOnPrimaryContainer : tone === SettingsCard.Secondary
        ? Appearance.colors.colOnSecondaryContainer : Appearance.colors.colOnLayer0
    readonly property color surfaceColor: tone === SettingsCard.Primary
        ? Appearance.colors.colPrimaryContainer : tone === SettingsCard.Secondary
        ? Appearance.colors.colSecondaryContainer : Appearance.colors.colBackgroundSurfaceContainer

    // Inherit configured transparency; optional surface opacity never fades content.
    color: tone === SettingsCard.Surface && surfaceOpacity === 1 ? baseSurfaceColor
        : Qt.rgba(surfaceColor.r, surfaceColor.g, surfaceColor.b,
                  baseSurfaceColor.a * Math.max(0, Math.min(1, surfaceOpacity)))
    radius: Appearance.rounding.large
    border.width: emphasized ? 1 : 0
    border.color: emphasized ? Appearance.colors.colPrimary : Appearance.colors.colLayer0Border
}
