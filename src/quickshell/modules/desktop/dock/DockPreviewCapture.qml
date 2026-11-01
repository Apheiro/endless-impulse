pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Wayland
import qs
import qs.services

// Render a single reduced frame offscreen in the already-mapped dock window.
Item {
    id: root
    x: -10000
    y: -10000
    width: 300
    height: 200
    readonly property bool canCapture: !!QsWindow.window?.visible && !GlobalStates.screenLocked
    property var completed: null
    property int generation: 0
    property bool grabbing: false
    readonly property bool debugCapture: Quickshell.env("AI_THUMBNAIL_DEBUG") === "1"
    Component.onCompleted: DockThumbnailCache.registerHost(root)
    Component.onDestruction: DockThumbnailCache.unregisterHost(root)

    function capture(toplevel, callback) {
        abort();
        completed = callback;
        generation++;
        deadline.restart();
        // live:false captures exactly one frame when a source is attached.
        if (debugCapture) console.log("THUMB_SOURCE", toplevel?.title, canCapture);
        view.captureSource = toplevel;
    }
    function finish(grab, width, height) {
        if (completed && debugCapture) console.log("THUMB_FINISH", !!grab, view.hasContent, view.sourceSize);
        const callback = completed;
        completed = null;
        generation++;
        grabbing = false;
        deadline.stop();
        view.captureSource = null;
        if (callback) callback(grab, width, height);
    }
    function abort() { finish(null, 0, 0); }
    function snapshot() {
        if (!completed || !view.hasContent || grabbing) return;
        grabbing = true;
        const token = generation;
        const size = Qt.size(Math.max(1, Math.round(view.width)), Math.max(1, Math.round(view.height)));
        if (!view.grabToImage(result => {
            if (!root || token !== root.generation) return;
            root.finish(result, size.width, size.height);
        }, size)) finish(null, 0, 0);
    }
    Timer { id: deadline; interval: 350; onTriggered: root.abort() }
    ScreencopyView {
        id: view
        width: Math.max(1, Math.round(implicitWidth))
        height: Math.max(1, Math.round(implicitHeight))
        constraintSize: Qt.size(300, 200)
        live: false
        paintCursor: false
        onHasContentChanged: { if (root.debugCapture) console.log("THUMB_CONTENT", hasContent); if (hasContent) Qt.callLater(root.snapshot); }
        onStopped: { if (root.debugCapture) console.log("THUMB_STOPPED"); root.abort(); }
    }
}
