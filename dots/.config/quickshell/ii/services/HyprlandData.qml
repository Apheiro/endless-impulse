pragma Singleton
pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import Quickshell.Hyprland
import "hyprland" as Ipc

/**
 * Provides access to some Hyprland data not available in Quickshell.Hyprland.
 */
Singleton {
    id: root
    property var windowList: []
    property var addresses: []
    property var windowByAddress: ({})
    property var workspaces: []
    property var workspaceIds: []
    property var workspaceById: ({})
    property var activeWorkspace: null
    property var monitors: []
    property var layers: ({})

    // Convenient stuff

    function toplevelsForWorkspace(workspace) {
        return ToplevelManager.toplevels.values.filter(toplevel => {
            const address = `0x${toplevel.HyprlandToplevel?.address}`;
            var win = HyprlandData.windowByAddress[address];
            return win?.workspace?.id === workspace;
        })
    }

    function hyprlandClientsForWorkspace(workspace) {
        return root.windowList.filter(win => win.workspace.id === workspace);
    }

    function clientForToplevel(toplevel) {
        if (!toplevel || !toplevel.HyprlandToplevel) {
            return null;
        }
        const address = `0x${toplevel?.HyprlandToplevel?.address}`;
        return root.windowByAddress[address];
    }

    // Coalesce bursts into bounded windows; never cancel an in-flight query.
    readonly property int clientsFlag: 1
    readonly property int workspacesFlag: 2
    readonly property int activeWorkspaceFlag: 4
    readonly property int monitorsFlag: 8
    readonly property int layersFlag: 16
    readonly property int allFlags: 31
    property int pendingUpdates: 0
    property var lastPayloads: ({})
    readonly property var queryJobs: [getClients, getWorkspaces, getActiveWorkspace, getMonitors, getLayers]

    function queueUpdates(flags) {
        pendingUpdates |= flags;
        // Starting only once avoids starvation during a continuous event stream.
        if (pendingUpdates && !refreshTimer.running) refreshTimer.start();
    }

    function flushUpdates() {
        for (const job of queryJobs) {
            if ((pendingUpdates & job.queryFlag) && !job.running) {
                pendingUpdates &= ~job.queryFlag;
                job.running = true;
            }
        }
        // Busy queries keep their pending bit and schedule it when they finish.
    }

    function queryFinished(name, exitCode) {
        if (exitCode !== 0) console.warn("[HyprlandData] Query failed:", name, exitCode);
        if (pendingUpdates && !refreshTimer.running) refreshTimer.start();
    }

    function updateWindowList() { queueUpdates(clientsFlag); }
    function updateLayers() { queueUpdates(layersFlag); }
    function updateMonitors() { queueUpdates(monitorsFlag); }
    function updateWorkspaces() { queueUpdates(workspacesFlag | activeWorkspaceFlag); }
    function updateAll() { queueUpdates(allFlags); }

    function handleEvent(name) {
        if (["submap", "activelayout", "screencast"].includes(name)) return;
        if (name === "configreloaded" || name.startsWith("monitor")) {
            updateAll();
        } else if (name === "openlayer" || name === "closelayer") {
            updateLayers();
        } else if (name === "focusedmon") {
            queueUpdates(monitorsFlag | workspacesFlag | activeWorkspaceFlag);
        } else if (name.startsWith("workspace") || name.startsWith("createworkspace")
                   || name.startsWith("destroyworkspace") || name.startsWith("moveworkspace")
                   || name === "renameworkspace" || name.startsWith("activespecial")) {
            queueUpdates(clientsFlag | workspacesFlag | activeWorkspaceFlag | monitorsFlag);
        } else if (name.startsWith("openwindow") || name.startsWith("closewindow") || name.startsWith("movewindow")) {
            queueUpdates(clientsFlag | workspacesFlag | activeWorkspaceFlag);
        } else if (name.startsWith("activewindow") || name === "fullscreen") {
            queueUpdates(clientsFlag | workspacesFlag | activeWorkspaceFlag);
        } else if (name.startsWith("window") || ["changefloatingmode", "pin", "urgent", "minimize", "moveintogroup", "moveoutofgroup", "togglegroup", "ignoregrouplock", "lockgroups"].includes(name)) {
            updateWindowList();
        } else {
            // Preserve correctness for new/unknown events instead of silently missing updates.
            updateAll();
        }
    }

    function applyResult(name, text) {
        const payload = text.trim();
        if (lastPayloads[name] === payload) return;
        try {
            const data = JSON.parse(payload);
            const listQuery = ["clients", "workspaces", "monitors"].includes(name);
            if (listQuery ? !Array.isArray(data) || data.some(item => item === null || typeof item !== "object")
                          : data === null || typeof data !== "object" || Array.isArray(data)) {
                throw new Error("Unexpected response type");
            }
            if (name === "clients") {
                const byAddress = {};
                for (const win of data) {
                    if (typeof win.address !== "string") throw new Error("Missing window address");
                    byAddress[win.address] = win;
                }
                root.windowList = data;
                root.windowByAddress = byAddress;
                root.addresses = data.map(win => win.address);
            } else if (name === "workspaces") {
                const valid = data.filter(ws => ws.id >= 1 && ws.id <= 100);
                const byId = {};
                for (const workspace of valid) byId[workspace.id] = workspace;
                root.workspaces = valid;
                root.workspaceById = byId;
                root.workspaceIds = valid.map(ws => ws.id);
            } else if (name === "activeworkspace") root.activeWorkspace = data;
            else if (name === "monitors") root.monitors = data;
            else if (name === "layers") root.layers = data;
            lastPayloads[name] = payload;
        } catch (error) {
            // A transient IPC failure must not clear the last valid desktop state.
            console.warn("[HyprlandData] Invalid response:", name, error.message);
        }
    }

    Timer {
        id: refreshTimer
        interval: 60
        onTriggered: root.flushUpdates()
    }

    function biggestWindowForWorkspace(workspaceId) {
        const windowsInThisWorkspace = HyprlandData.windowList.filter(w => w.workspace.id == workspaceId);
        return windowsInThisWorkspace.reduce((maxWin, win) => {
            const maxArea = (maxWin?.size?.[0] ?? 0) * (maxWin?.size?.[1] ?? 0);
            const winArea = (win?.size?.[0] ?? 0) * (win?.size?.[1] ?? 0);
            return winArea > maxArea ? win : maxWin;
        }, null);
    }

    Component.onCompleted: {
        for (const job of queryJobs) {
            job.resultReceived.connect(root.applyResult);
            job.finished.connect(root.queryFinished);
        }
        updateAll();
    }

    Connections {
        target: Hyprland
        function onRawEvent(event) { root.handleEvent(event.name); }
    }

    Ipc.QueryProcess { id: getClients; queryName: "clients"; queryFlag: root.clientsFlag }
    Ipc.QueryProcess { id: getWorkspaces; queryName: "workspaces"; queryFlag: root.workspacesFlag }
    Ipc.QueryProcess { id: getActiveWorkspace; queryName: "activeworkspace"; queryFlag: root.activeWorkspaceFlag }
    Ipc.QueryProcess { id: getMonitors; queryName: "monitors"; queryFlag: root.monitorsFlag }
    Ipc.QueryProcess { id: getLayers; queryName: "layers"; queryFlag: root.layersFlag }
}
