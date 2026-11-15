pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Hyprland
import qs.services

// Preserve the caller's desired grab across authentication. Disabling a native
// grab can itself emit cleared: only forward genuine clears while armed.
Scope {
    id: root
    property bool active: false
    property bool suspended: AuthenticationFocusState.active
    property alias windows: grab.windows
    signal cleared()
    property bool armed: false
    // Do not acquire a native grab until the first snapshot: a subscriber may
    // be opening while a remote authentication panel is already visible.
    readonly property bool grabbing: active && !suspended && AuthenticationFocusState.grabReady
    onGrabbingChanged: {
        armed = false;
        if (grabbing) Qt.callLater(() => { if (root.grabbing) root.armed = true; });
    }
    Component.onCompleted: {
        if (grabbing) Qt.callLater(() => { if (root.grabbing) root.armed = true; });
    }
    function requestFocus() {
        root.active = true;
        root.armed = false;
        Qt.callLater(() => { if (root.grabbing) root.armed = true; });
        grab.active = Qt.binding(() => root.grabbing);
    }
    HyprlandFocusGrab {
        id: grab
        active: root.grabbing
        onCleared: {
            if (root.armed && root.grabbing && !root.suspended) {
                root.armed = false;
                root.cleared();
            }
        }
    }
}
