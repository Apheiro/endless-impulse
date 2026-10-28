pragma Singleton
pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland

Singleton {
    id: root
    property var minimized: []
    property string error: ""
    property string errorAddress: ""
    property bool capturing: false
    readonly property bool busy: worker.running || capturing
    readonly property string workspace: "special:artificial-minimized"
    function address(toplevel) {
        const value = toplevel?.HyprlandToplevel?.address;
        if (!value) return "";
        const id = String(value).startsWith("0x") ? String(value) : "0x" + value;
        return /^0x0+$/.test(id) ? "" : id;
    }
    function isMinimized(toplevel) {
        const id = address(toplevel);
        return minimized.includes(id) || HyprlandData.windowByAddress[id]?.workspace?.name === workspace;
    }
    function request(action, toplevel) {
        if (busy) return;
        const id = address(toplevel);
        if (action !== "status" && !id) { toplevel?.activate(); return; }
        if (action !== "status") { error = ""; errorAddress = id; }
        worker.received = false;
        worker.command = ["python3", Quickshell.shellPath("scripts/hyprland/minimize.py"), action];
        if (id) worker.command = [...worker.command, id];
        worker.running = true;
    }
    function captureThen(action, toplevel) {
        if (busy) return;
        capturing = true;
        DockThumbnailCache.capture(toplevel, () => {
            root.capturing = false;
            root.request(action, toplevel);
        });
    }
    function toggle(toplevel) {
        if (!isMinimized(toplevel) && toplevel?.activated) captureThen("toggle", toplevel);
        else request("toggle", toplevel);
    }
    function activate(toplevel) { request("restore", toplevel); }
    function minimize(toplevel) {
        if (isMinimized(toplevel)) request("restore", toplevel);
        else captureThen("minimize", toplevel);
    }
    Component.onCompleted: refresh.restart()
    Process {
        id: worker
        property bool received: false
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const result = JSON.parse(text);
                    worker.received = true;
                    if (result.ok) root.minimized = result.minimized;
                    else { root.error = result.error; console.warn("[Minimize]", result.error); }
                } catch (error) { root.error = String(error); }
            }
        }
        onExited: {
            if (!received) root.error = "Could not communicate with Hyprland";
            HyprlandData.updateWindowList();
            if (refreshPending) { refreshPending = false; refresh.restart(); }
        }
    }
    property bool refreshPending: false
    Timer { id: refresh; interval: 120; onTriggered: { if (root.busy) root.refreshPending = true; else root.request("status"); } }
    Connections {
        target: Hyprland
        function onRawEvent(event) {
            if (["movewindow", "movewindowv2", "closewindow", "configreloaded"].includes(event.name)) refresh.restart();
        }
    }
}
