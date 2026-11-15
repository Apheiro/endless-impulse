pragma Singleton
pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root
    property bool active: false
    property bool ready: false
    property bool loading: false
    property bool scanning: false
    property bool cancelling: false
    property bool stale: false
    property string scanStatus: ""
    property string analysisState: "idle"
    property var diagnostic: null
    readonly property bool hasComplete: isResultState(summary?.state) && isResultState(view?.state)
    readonly property bool hasWarnings: hasComplete && summary.coverageIncomplete
    readonly property bool hasChanges: hasComplete && summary.changesObserved
    property bool fromCache: false
    property int workers: 0 // 0 preserves the native environment/default (2).
    function isResultState(state) { return ["complete", "complete-with-warnings"].includes(state); }

    property string error: ""
    property string warning: ""
    property var backend: ({available: false, error: "native-engine-required", version: ""})
    property var disks: []
    property var volumes: []
    property string selectedId: ""
    readonly property var selected: volumes.find(v => v.id === selectedId) || disks.find(d => d.id === selectedId) || null
    property var view: null
    property var summary: null
    property var progress: ({entries: 0, bytes: 0, elapsed: 0})
    property string order: "size"
    property string query: ""
    property bool othersOnly: false
    property real chartWidth: 800
    onChartWidthChanged: if (active && view && !scanning) segmentLayout.restart()
    property string highlightedPath: ""
    property int highlightedNodeId: -1
    property int sequence: 0
    property int scanId: -1
    property string scanVolume: ""
    property int viewId: -1
    property int inventoryId: -1
    property bool pendingSelection: false
    property bool pendingRetry: false
    property string requestedPath: ""
    property string currentMountToken: ""
    property var presentationCache: ({})

    function send(action, data = {}) {
        if (!ready) return -1;
        const id = ++sequence;
        worker.write(JSON.stringify(Object.assign({action, id}, data)) + "\n");
        return id;
    }
    function refresh() {
        if (!ready) { restart(); return; }
        if (loading || scanning) return;
        error = ""; loading = true;
        inventoryId = send("inventory");
        inventoryDeadline.restart();
        if (summary) stale = true;
    }
    function savePresentation() {
        if (!hasComplete || !selectedId) return;
        const cache = Object.assign({}, presentationCache);
        delete cache[selectedId];
        cache[selectedId] = {view, summary, query, order, othersOnly, mountToken: selected?.mountToken};
        const keys = Object.keys(cache);
        while (keys.length > 3) delete cache[keys.shift()];
        presentationCache = cache;
    }
    function select(identity) {
        if (identity === selectedId && view) {
            if (!scanning) { pendingSelection = true; activation.restart(); }
            return;
        }
        savePresentation();
        pendingRetry = false;
        selectedId = identity;
        error = ""; scanStatus = ""; diagnostic = null; query = ""; othersOnly = false; highlightedPath = ""; highlightedNodeId = -1; stale = false;
        viewId = -1;
        const cached = presentationCache[identity];
        view = cached && isResultState(cached.summary?.state) && isResultState(cached.view?.state) && cached.mountToken === selected?.mountToken ? cached.view : null;
        summary = view ? cached.summary : null;
        fromCache = !!view;
        if (view) { query = cached.query || ""; order = cached.order || "size"; othersOnly = !!cached.othersOnly; }
        analysisState = hasComplete ? summary.state : selected?.mounted ? "loading" : "unmounted";
        progress = {entries: 0, directories: 0, bytes: 0, elapsed: 0};
        currentMountToken = selected?.mountToken || "";
        requestedPath = view?.path || selected?.mount || "";
        pendingSelection = true;
        if (scanning) cancel(false);
        activation.restart();
    }
    function activateSelection() {
        if (!active || !ready || loading || scanning || !pendingSelection) return;
        pendingSelection = false;
        if (!selected?.mounted) return;
        if (!backend.available) { failAnalysis(backend.error || "native-engine-required"); return; }
        viewId = send("open", {volume: selectedId, path: requestedPath || selected.mount, snapshot: summary?.scanId || "", scopeRoot: summary?.root || "", nodeId: view?.nodeId, offset: view?.offset || 0, order, query, others: othersOnly, width: chartWidth});
    }
    function analyze(path = "") {
        if (!active || !selected?.mounted || !backend.available || scanning || loading || !ready) return;
        requestedPath = path || view?.path || selected.mount;
        error = ""; scanStatus = ""; diagnostic = null; stale = hasComplete; analysisState = "running";
        scanning = true; cancelling = false;
        progress = {entries: 0, directories: 0, bytes: 0, elapsed: 0};
        scanVolume = selectedId;
        viewId = -1;
        scanId = send("scan", {volume: selectedId, path: requestedPath, order, width: chartWidth, workers});
        scanDeadline.interval = 15000;
        scanDeadline.restart();
    }
    function cancel(manual = true) {
        if (manual) { pendingSelection = false; pendingRetry = false; }
        if (!scanning) {
            if (analysisState === "loading") { activation.stop(); viewId = -1; failAnalysis("cancelled", "cancelled"); }
            return;
        }
        if (cancelling) return;
        cancelling = true;
        send("cancel");
        scanDeadline.interval = 3000;
        scanDeadline.restart();
    }
    function browse(path, offset = 0, preserveFilter = false, nodeId = null) {
        if (!ready || !selected?.mounted) return;
        if (!preserveFilter) { query = ""; othersOnly = false; }
        if (!preserveFilter) { highlightedPath = ""; highlightedNodeId = -1; }
        pendingSelection = false; activation.stop();
        requestedPath = path;
        viewId = send("open", {volume: selectedId, path, snapshot: summary?.scanId || "", scopeRoot: summary?.root || "", nodeId: nodeId === null && path === view?.path ? view.nodeId : nodeId, offset, order, query, others: othersOnly, width: chartWidth});
    }
    function retry() {
        if (ready) analyze(requestedPath);
        else { pendingRetry = true; restart(); }
    }
    function acceptResult(data, fresh = false) {
        if (!isResultState(data.summary?.state) || data.summary.protocol !== 1 || !data.summary.scanId
                || !["finished", "finished-with-warnings"].includes(data.summary.engineState)
                || data.view?.state !== data.summary.state || data.view?.scanId !== data.summary.scanId
                || (data.summary.state === "complete" && (data.summary.engineState !== "finished" || data.summary.unreadableCount > 0 || data.summary.coverageIncomplete))
                || (data.summary.state === "complete-with-warnings" && (!data.summary.coverageIncomplete || !(data.summary.unreadableCount > 0) || data.summary.engineState !== "finished-with-warnings"))) {
            failAnalysis("invalid-completion", "error", data.summary);
            return false;
        }
        if (data.viewReset) { query = ""; othersOnly = false; highlightedPath = ""; highlightedNodeId = -1; }
        summary = data.summary; view = data.view; fromCache = !fresh;
        if (fresh || ["loading", "idle"].includes(analysisState)) {
            stale = false; analysisState = data.summary.state; scanStatus = ""; error = ""; diagnostic = null;
        }
        savePresentation();
        return true;
    }
    function failAnalysis(code, state = "error", details = null) {
        error = code; scanStatus = code; diagnostic = details;
        analysisState = state; stale = hasComplete;
    }
    function filterFolders(text) { query = text; filterDelay.restart(); }
    function showOthers() { highlightedPath = ""; highlightedNodeId = -1; othersOnly = true; query = ""; browse(view.path, 0, true); }
    function formatBytes(value) {
        if (value === undefined || value === null) return "—";
        const units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"];
        let unit = 0;
        while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit++; }
        return value.toLocaleString(Qt.locale(), "f", unit ? 1 : 0) + " " + units[unit];
    }
    function exact(value) { return Number(value || 0).toLocaleString(Qt.locale(), "f", 0) + " B"; }
    // A hidden page cancels the native scan but keeps the idle session cache for
    // returning to this page within the same Settings session.
    onActiveChanged: {
        if (active) {
            if (!worker.running) worker.running = true;
            else if (ready) { pendingSelection = true; activation.restart(); }
        } else { activation.stop(); filterDelay.stop(); segmentLayout.stop(); viewId = -1; pendingSelection = false; cancel(); }
    }
    function stop() {
        inventoryDeadline.stop(); scanDeadline.stop();
        ready = false; loading = false; scanning = false; cancelling = false;
        scanId = -1; viewId = -1;
        worker.running = false;
    }
    function restart() { stop(); if (active) Qt.callLater(() => worker.running = true); }
    Timer { id: activation; interval: 180; onTriggered: root.activateSelection() }
    Timer { id: segmentLayout; interval: 150; onTriggered: if (root.active && root.view && !root.scanning) root.browse(root.view.path, root.view.offset, true) }
    Timer { id: filterDelay; interval: 180; onTriggered: if (root.view) root.browse(root.view.path, 0, true) }
    Timer {
        id: inventoryDeadline; interval: 10000
        onTriggered: { root.error = "backend-timeout"; root.stop(); }
    }
    Timer {
        id: scanDeadline
        onTriggered: {
            const switching = root.pendingSelection;
            root.failAnalysis(root.cancelling ? "cancelled" : "worker-unresponsive", root.cancelling ? "cancelled" : "error");
            root.stop();
            if (switching && root.active) root.restart();
        }
    }
    Process {
        id: worker
        command: ["python3", Quickshell.shellPath("scripts/storage/control.py")]
        stdinEnabled: true
        stdout: SplitParser {
            onRead: line => {
                try {
                    const data = JSON.parse(line);
                    if (data.event === "ready") { root.ready = true; root.refresh(); }
                    else if (data.event === "inventory" && data.id === root.inventoryId) {
                        inventoryDeadline.stop(); root.loading = false;
                        root.disks = data.disks || []; root.volumes = data.volumes; root.warning = data.warning || ""; root.backend = data.backend;
                        if (!root.selectedId) root.select(root.volumes.find(v => v.mount === "/" || v.name === "System")?.id || root.volumes[0]?.id || root.disks[0]?.id || "");
                        else if (!root.selected) { root.view = null; root.summary = null; root.failAnalysis("volume-disconnected"); }
                        else if (!root.view || root.currentMountToken !== (root.selected?.mountToken || "")) {
                            root.view = null; root.summary = null;
                            root.currentMountToken = root.selected?.mountToken || "";
                            root.requestedPath = root.selected?.mount || "";
                            root.pendingSelection = true; activation.restart();
                        }
                        if (root.pendingRetry && root.active && root.selected?.mounted) {
                            root.pendingRetry = false;
                            Qt.callLater(() => root.analyze(root.requestedPath));
                        } else if (root.pendingSelection && root.active) activation.restart();
                    } else if (data.event === "progress" && data.id === root.scanId) {
                        if (root.scanVolume === root.selectedId) root.progress = data;
                        if (!root.cancelling) { scanDeadline.interval = 15000; scanDeadline.restart(); }
                    } else if ((data.event === "complete" || data.event === "analysis-failed") && data.id === root.scanId) {
                        scanDeadline.stop(); root.scanning = false; root.cancelling = false;
                        if (data.volume === root.selectedId) {
                            if (data.event === "complete") root.acceptResult(data, true);
                            else root.failAnalysis(data.error, data.state, data.diagnostic);
                        }
                        activation.restart();
                    } else if (data.event === "view" && data.id === root.viewId) {
                        root.acceptResult(data);
                    } else if (data.event === "cache-miss" && data.id === root.viewId) {
                        if (root.active && !root.scanning) root.analyze(root.summary?.root || data.path);
                    } else if (data.event === "error" && [root.scanId, root.viewId, root.inventoryId].includes(data.id)) {
                        const oldSelection = data.id === root.scanId && root.scanVolume !== root.selectedId;
                        if (!oldSelection) root.failAnalysis(data.error);
                        if (data.id === root.scanId) { scanDeadline.stop(); root.scanning = false; root.cancelling = false; activation.restart(); }
                        if (data.id === root.inventoryId) { inventoryDeadline.stop(); root.loading = false; }
                        if (!oldSelection && ["volume-disconnected", "outside-volume"].includes(data.error)) { root.view = null; root.summary = null; }
                    }
                } catch (e) { root.failAnalysis("invalid-backend-response"); root.stop(); }
            }
        }
        stderr: StdioCollector {}
        onExited: {
            if (root.ready || root.loading || root.scanning || (root.active && !root.error)) {
                root.failAnalysis("backend-stopped"); root.ready = false; root.scanning = false; root.loading = false; root.cancelling = false;
                inventoryDeadline.stop(); scanDeadline.stop();
            }
        }
    }
}
