pragma Singleton
pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root
    property bool active: false
    readonly property bool busy: worker.running
    property string error: ""
    property string result: ""
    property bool retryRequired: false
    property string monitorStatus: "inactive"
    property var snapshot: ({devices: [], warnings: [], tools: {}})
    property var detail: null
    property var drafts: []
    property var preview: null
    property string selectedId: ""
    property bool pendingRefresh: false
    property bool pendingDetail: false
    property bool pendingDrafts: false
    property var request: ({})
    property bool received: false
    property bool timedOut: false

    function start(payload) {
        if (busy) return false;
        request = payload;
        error = "";
        result = "";
        received = false;
        timedOut = false;
        worker.command = ["python3", Quickshell.shellPath("scripts/hardware/control.py"), "--request", JSON.stringify(payload)];
        worker.running = true;
        deadline.restart();
        return true;
    }
    function refresh(manual = true) {
        if (!manual && retryRequired) return;
        if (manual) retryRequired = false;
        if (busy) { pendingRefresh = true; return; }
        pendingRefresh = false;
        start({action: "snapshot"});
    }
    signal selectionRequested()
    function select(identity) {
        selectionRequested();
        selectedId = identity;
        detail = null;
        retryRequired = false;
        if (busy) pendingDetail = true;
        else { pendingDetail = false; start({action: "detail", id: identity}); }
    }
    function loadDrafts() {
        if (busy) pendingDrafts = true;
        else start({action: "drafts"});
    }
    function validateRule(rule) { preview = null; start({action: "preview", rule}); }
    function savePreview() {
        if (preview && !busy) start({action: "save", rule: preview.rule});
    }
    function removeDraft(identity) { preview = null; start({action: "delete", id: identity}); }
    function setDraftEnabled(rule, enabled) { preview = null; start({action: "save", rule: Object.assign({}, rule, {enabled})}); }
    function restoreDrafts() { preview = null; start({action: "restore"}); }
    // Index once per snapshot; filtering and branch traversal reuse these maps.
    property var nodeIndex: ({})
    property var nodeChildren: ({})
    property var entityIndex: ({})
    property var entityChildren: ({})
    readonly property var projection: snapshot.projection || ({entities: [], categories: [], ownerByNode: {}, componentCount: 0, rawNodeCount: 0})
    readonly property var selectedNode: nodeIndex[selectedId] || null
    readonly property var selectedEntity: entityIndex[projection.ownerByNode[selectedId]] || null
    onSnapshotChanged: rebuildIndex()
    function rebuildIndex() {
        const nodes = {}, children = {}, entities = {}, connections = {};
        (snapshot.devices || []).forEach(d => {
            nodes[d.id] = d;
            if (!children[d.parent]) children[d.parent] = [];
            children[d.parent].push(d);
        });
        (snapshot.projection?.entities || []).forEach(e => {
            entities[e.id] = e;
            if (!connections[e.parent]) connections[e.parent] = [];
            connections[e.parent].push(e);
        });
        nodeIndex = nodes; nodeChildren = children;
        entityIndex = entities; entityChildren = connections;
    }
    function interfaces(identity) {
        const e = entityIndex[identity];
        return (e?.interfaceIds || []).map(id => nodeIndex[id]).filter(n => !!n);
    }
    function browse(mode, query, category, expanded, budget = 60, offset = 0) {
        budget = Math.max(1, Math.min(600, budget));
        const terms = query.toLowerCase().trim().split(/\s+/).filter(t => !!t);
        const raw = mode === "technical";
        const source = raw ? snapshot.devices : projection.entities;
        const index = raw ? nodeIndex : entityIndex;
        const children = raw ? nodeChildren : entityChildren;
        const rows = [];
        let total = 0;
        function append(d, depth) {
            total++;
            if (total > offset && rows.length < budget) rows.push(Object.assign({}, d, {
                depth, hasChildren: !!children[d.id]?.length,
                breadcrumb: d.breadcrumb || d.id,
                category: d.category || "Other"
            }));
        }
        if (terms.length || mode === "categories") {
            source.forEach(d => {
                if (!raw && (category ? d.category !== category : ["Other", "Virtual"].includes(d.category) && !terms.length)) return;
                const text = (d.searchText || [d.name, d.id, d.kernel, d.driver].join(" ")).toLowerCase();
                if (terms.every(t => text.includes(t))) append(d, 0);
            });
        } else {
            // Visit only expanded branches; do not construct a thousand-row flat tree.
            const stack = (children[""] || []).slice().reverse().map(d => ({d, depth: 0}));
            while (stack.length) {
                const {d, depth} = stack.pop();
                if (!raw && d.virtual && !expanded["virtual"]) continue;
                append(d, depth);
                if (expanded[d.id]) {
                    const branch = children[d.id] || [];
                    for (let i = branch.length - 1; i >= 0; i--) stack.push({d: branch[i], depth: depth + 1});
                }
            }
        }
        return {rows, total, more: total > offset + rows.length};
    }
    function reveal(identity, technical = false) {
        const result = {}, index = technical ? nodeIndex : entityIndex;
        let current = index[identity];
        while (current && current.parent) {
            result[current.parent] = true;
            current = index[current.parent];
        }
        return result;
    }
    function notifyHotplug() {
        if (active && !retryRequired && !hotplug.running) hotplug.start();
    }
    onActiveChanged: {
        if (active) { pendingDrafts = true; refresh(); }
        else { hotplug.stop(); pendingRefresh = false; }
    }
    Timer {
        id: hotplug
        interval: 750
        onTriggered: if (root.active) root.refresh(false)
    }
    Timer {
        id: deadline
        interval: 20000
        onTriggered: {
            root.timedOut = true;
            root.retryRequired = true;
            root.error = "backend-timeout";
            worker.running = false;
        }
    }
    Process {
        id: monitor
        running: root.active
        command: ["udevadm", "monitor", "--udev"]
        onStarted: root.monitorStatus = "listening"
        onExited: root.monitorStatus = root.active ? "unavailable" : "inactive"
        stdout: SplitParser {
            onRead: line => {
                // Bounded coalescing: continuous events cannot starve refreshes.
                if (line.startsWith("UDEV")) root.notifyHotplug();
            }
        }
        stderr: StdioCollector {}
    }
    Process {
        id: worker
        stdout: StdioCollector {
            onStreamFinished: {
                if (root.timedOut) return;
                try {
                    const response = JSON.parse(text);
                    root.received = true;
                    if (!response.ok) {
                        root.error = response.error || "backend-failed";
                        if (["snapshot", "detail"].includes(root.request.action)) root.retryRequired = true;
                        return;
                    }
                    if (response.snapshot) {
                        root.snapshot = response.snapshot;
                        if (root.selectedId && !response.snapshot.devices.some(d => d.id === root.selectedId)) {
                            root.detail = null;
                            root.error = "device-disconnected";
                        } else if (root.selectedId) root.pendingDetail = true;
                    }
                    if (response.detail && response.detail.id === root.selectedId) root.detail = response.detail;
                    if (response.drafts) {
                        root.drafts = response.drafts;
                        if (["save", "delete", "restore"].includes(root.request.action)) {
                            root.result = "drafts-saved-and-verified";
                            root.preview = null;
                        }
                    }
                    if (response.preview) root.preview = response.preview;
                } catch (e) { root.error = "invalid-backend-response"; root.retryRequired = true; }
            }
        }
        stderr: StdioCollector {}
        onExited: {
            deadline.stop();
            if (!root.received && !root.timedOut) { root.error = "backend-no-response"; root.retryRequired = true; }
            Qt.callLater(() => {
                if (root.busy) return;
                if (root.pendingDrafts) { root.pendingDrafts = false; root.loadDrafts(); }
                else if (root.pendingDetail && root.selectedId && !root.retryRequired) { root.pendingDetail = false; root.start({action: "detail", id: root.selectedId}); }
                else if (root.pendingRefresh && root.active && !root.retryRequired) root.refresh(false);
            });
        }
    }
}
