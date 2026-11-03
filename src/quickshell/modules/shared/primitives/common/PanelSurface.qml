import QtQuick
import qs.modules.shared

// Window/panel background only. Geometry, input, masks and compositor effects
// belong to the consumer. Keep Rectangle's native content and sizing semantics.
Rectangle {
    id: root

    enum Variant { Solid, Translucent, Glass }
    enum VisualState { Normal, Emphasized, Selected, Focused, Disabled }

    property int variant: PanelSurface.Translucent
    property int visualState: PanelSurface.Normal

    // Glass deliberately has the same fallback as Translucent. This expresses
    // intent; it cannot enable or inspect compositor blur for an individual item.
    readonly property color baseColor: variant === PanelSurface.Solid
        ? Qt.rgba(Appearance.colors.colLayer0Base.r, Appearance.colors.colLayer0Base.g, Appearance.colors.colLayer0Base.b, 1)
        : Appearance.colors.colLayer0
    readonly property color foreground: visualState === PanelSurface.Selected
        ? Appearance.colors.colOnPrimaryContainer
        : visualState === PanelSurface.Disabled ? Appearance.colors.colSubtext : Appearance.colors.colOnLayer0

    color: visualState === PanelSurface.Selected
        ? Qt.rgba(Appearance.colors.colPrimaryContainer.r, Appearance.colors.colPrimaryContainer.g, Appearance.colors.colPrimaryContainer.b, baseColor.a)
        : baseColor
    radius: Appearance.rounding.large
    border.width: 1
    border.color: visualState === PanelSurface.Emphasized || visualState === PanelSurface.Focused
        || visualState === PanelSurface.Selected ? Appearance.colors.colPrimary : Appearance.colors.colLayer0Border
}
