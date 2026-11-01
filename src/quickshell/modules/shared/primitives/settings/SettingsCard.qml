import QtQuick
import qs.modules.shared

// A content surface placed over the Settings window's colLayer0 base.
Rectangle {
    property bool emphasized: false
    color: Appearance.colors.colBackgroundSurfaceContainer
    radius: Appearance.rounding.large
    border.width: emphasized ? 1 : 0
    border.color: emphasized ? Appearance.colors.colPrimary : Appearance.colors.colLayer0Border
}
