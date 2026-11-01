import QtQuick
import qs.modules.shared

// Keep the surface mapped through the exit so Hyprland can blur live windows.
QtObject {
    id: root
    required property bool opened
    readonly property bool visible: opened || revealAnimation.running || progress !== 0
    property real progress: opened ? 1 : 0

    Behavior on progress {
        id: progressBehavior
        NumberAnimation {
            id: revealAnimation
            // Use the destination: opened and its dependent bindings may update
            // in different orders when the Behavior starts.
            duration: Appearance.animationDurationFor(progressBehavior.targetValue === 1 ? "sidebarOpen" : "sidebarClose")
            easing.type: Easing.BezierSpline
            easing.bezierCurve: Appearance.animationCurves.sidebarSlide
        }
    }
}
