import QtQuick
import qs.modules.shared

// Place before the target as a sibling, with room for shadow outside its bounds.
// External placement preserves clipping, stacking and independent transforms.
StyledRectangularShadow {
    property real elevation: 1

    visible: elevation > 0 && target.visible
    blur: 0.9 * Appearance.sizes.elevationMargin * Math.max(0, elevation)
    spread: Math.max(0, elevation)
    offset: Qt.vector2d(0, Math.max(0, elevation))
}
