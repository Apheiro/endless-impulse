pragma Singleton
pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root

    property bool active: false
    property bool busy: false
    // Set only by the bridge's permission challenge, never by ordinary reads.
    property bool authorizing: false
    property bool retryRequired: false
    property bool workerReady: false
    property int requestSerial: 0
    readonly property bool editable: !busy && snapshot.connected && snapshot.complete
    property string error: ""
    property string lastValidRead: ""
    property bool refreshing: false
    property var request: ({})
    property string result: ""
    property var definition: null
    property var definitionContext: null
    property var snapshot: ({
                                connected: false,
                                complete: false,
                                state: "connecting",
                                scopes: {},
                                services: [],
                                activeZones: [],
                                differences: []
                            })

    function apply(change) {
        if (!editable)
            return;
        result = "";
        definition = null;
        start(Object.assign({}, change, {
                                confirmed: true,
                                allowInteraction: true
                            }));
    }
    function refresh(manual = true) {
        if (busy || (!manual && retryRequired))
            return;
        if (manual) retryRequired = false;
        refreshing = true;
        start({
                  action: "snapshot",
                  // First entry and manual Refresh may open native Polkit
                  // immediately. Timer reads stay silent; cancellation gates re-entry.
                  allowInteraction: manual
              });
    }
    function inspect(kind, name, scope) {
        if (busy) return;
        definition = null;
        definitionContext = {kind, name, scope};
        start({action: "inspect", kind, name, scope, allowInteraction: false});
    }
    function start(payload) {
        if (busy) return;
        busy = true;
        error = "";
        request = Object.assign({}, payload, {requestId: ++requestSerial});
        watchdog.restart();
        if (workerReady && process.running)
            process.write(JSON.stringify(request) + "\n");
        else
            process.running = true;
    }
    function invalidate(message, state = "communication-error") {
        authorizing = false;
        busy = false;
        refreshing = false;
        retryRequired = true;
        definition = null;
        snapshot = {connected: false, complete: false, state, scopes: {}, services: [], activeZones: [], differences: []};
        error = message;
        watchdog.stop();
    }
    function stopWorker(message, state = "communication-error") {
        workerReady = false;
        invalidate(message, state);
        process.running = false;
    }

    onActiveChanged: {
        if (active && !busy) {
            result = "";
            if (!retryRequired) snapshot = {
                connected: false,
                complete: false,
                state: "connecting",
                scopes: {},
                services: [],
                activeZones: [],
                differences: []
            };
            refresh(!retryRequired);
        }
    }

    Timer {
        id: watchdog
        // Service deadlines are wall time, independent of animation speed.
        interval: 300000
        onTriggered: root.stopWorker("Firewalld bridge timed out. A change may have taken effect; refresh and inspect before retrying.", "timeout")
    }

    Timer {
        interval: 30000
        repeat: true
        running: root.active && !root.busy && !root.retryRequired

        onTriggered: root.refresh(false)
    }

    Process {
        id: process

        // Retain the Polkit subject across reads, writes and page navigation.
        // An idle worker performs no I/O. Process destruction closes it with Settings.
        command: ["python3", Quickshell.shellPath("scripts/firewalld/control.py"), "--serve"]

        stdinEnabled: true
        stdout: SplitParser {
            onRead: data => {
                try {
                    const response = JSON.parse(data);
                    if (!response || typeof response !== "object") throw new Error("Invalid response");
                    if (response.event === "ready") {
                        if (root.workerReady) throw new Error("Duplicate ready event");
                        root.workerReady = true;
                        if (root.busy) process.write(JSON.stringify(root.request) + "\n");
                        return;
                    }
                    if (!root.workerReady && response.ok === false) {
                        root.stopWorker(response.error || "Could not start the Firewalld bridge", response.operationState || "communication-error");
                        return;
                    }
                    if (response.requestId === undefined) throw new Error("Missing request ID");
                    // An old/duplicate response must never resolve another request.
                    if (response.requestId !== root.request.requestId || !root.busy) return;
                    if (response.event === "authorization-required") {
                        if (!root.request.allowInteraction || root.authorizing) throw new Error("Unexpected authorization");
                        root.authorizing = true;
                        // Let the Settings binding release the grab before the
                        // bridge launches a CLI that may open the system agent.
                        const requestId = response.requestId;
                        Qt.callLater(() => {
                            if (process.running && root.busy && root.authorizing && root.request.requestId === requestId)
                                process.write(JSON.stringify({event: "authorize", requestId}) + "\n");
                        });
                        return;
                    }
                    if (typeof response.ok !== "boolean" || response.event) throw new Error("Invalid result");
                    if (response.ok && root.request.action === "snapshot" && !response.snapshot) throw new Error("Missing snapshot");
                    if (response.ok && root.request.action === "inspect" && (!response.definition?.fields || response.definition.name !== root.request.name)) throw new Error("Invalid definition");
                    if (response.snapshot && (typeof response.snapshot.complete !== "boolean" || typeof response.snapshot.connected !== "boolean" || !response.snapshot.scopes)) throw new Error("Invalid snapshot");
                    watchdog.stop();
                    root.authorizing = false;
                    root.busy = false;
                    root.refreshing = false;
                    if (root.request.action === "inspect") {
                        root.definition = response.ok ? response.definition : null;
                        root.error = response.error || "";
                        if (!response.ok) root.invalidate(root.error, response.operationState || "communication-error");
                        return;
                    }
                    if (response.snapshot) {
                        root.snapshot = response.snapshot;
                        if (response.snapshot.lastUpdated)
                            root.lastValidRead = response.snapshot.lastUpdated;
                    }
                    if (!response.snapshot && !response.ok)
                        root.invalidate(response.error || "Firewalld request failed", response.operationState || "communication-error");
                    root.error = response.error || response.snapshot?.error || "";
                    root.retryRequired = !response.ok || !response.snapshot?.complete;
                    if (root.request.action !== "snapshot")
                        root.result = response.ok ? response.operationState : "failed";
                } catch (e) {
                    root.stopWorker("Invalid bridge response. Refresh and inspect before retrying.");
                }
            }
        }

        onExited: (exitCode, exitStatus) => {
            const incomplete = root.busy || root.snapshot.complete;
            root.workerReady = false;
            root.authorizing = false;
            root.busy = false;
            root.refreshing = false;
            watchdog.stop();
            if (incomplete) {
                root.invalidate("Firewalld bridge exited unexpectedly. A change may have taken effect; refresh and inspect before retrying.");
            }
        }
    }
}
