pragma Singleton
pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland

Singleton {
    id: root
    property var monitors: []
    property var devices: []
    property var fields: []
    property var values: ({})
    property var supported: ({})
    property var saved: ({options: {}, monitors: {}, devices: {}})
    property var draft: ({options: {}, monitors: {}, devices: {}})
    property var transaction: null
    property bool integrated: false
    property bool loaded: false
    property bool refreshPending: false
    property bool resolvingTransaction: false
    property var pendingResolution: null
    property bool transactionPollingPaused: false
    readonly property bool restorationFailed: transaction?.phase === "restore_failed" || transactionPollingPaused
    property double lastTransactionPoll: 0
    property bool failed: false
    property string message: ""
    property double now: Date.now()
    property bool requestInFlight: false
    readonly property bool busy: requestInFlight
    readonly property int remaining: transaction ? Math.max(0, Math.ceil(transaction.deadline - now / 1000)) : 0
    readonly property int changes: Object.keys(draft.options).length + Object.keys(draft.monitors).length + Object.keys(draft.devices).length

    Component.onCompleted: request("transaction")

    function option(key) {
        return Object.prototype.hasOwnProperty.call(draft.options, key) && draft.options[key] !== null ? draft.options[key] : values[key];
    }
    function put(section, key, value) {
        const next = JSON.parse(JSON.stringify(draft));
        next[section][key] = value;
        draft = next;
    }
    function discard() {
        draft = {options: {}, monitors: {}, devices: {}};
    }
    function monitor(name) {
        return draft.monitors[name] ?? monitors.find(monitor => monitor.name === name)?.current ?? {};
    }
    function putMonitor(name, changes) {
        put("monitors", name, Object.assign({}, monitor(name), changes));
    }
    function deviceValue(name, field) {
        if (Object.prototype.hasOwnProperty.call(draft.devices, name)) {
            return draft.devices[name]?.[field.key] ?? values["input:" + field.key];
        }
        return saved.devices[name]?.[field.key] ?? values["input:" + field.key];
    }
    function putDevice(name, key, value) {
        const previous = Object.prototype.hasOwnProperty.call(draft.devices, name) ? draft.devices[name] : saved.devices[name];
        put("devices", name, Object.assign({}, previous ?? {}, {[key]: value}));
    }
    function deviceFields(kind) {
        const keys = kind === "keyboards" ? ["kb_layout", "kb_variant", "kb_options", "repeat_delay", "repeat_rate", "numlock_by_default"]
            : ["sensitivity", "accel_profile", "left_handed", "natural_scroll"];
        return keys.map(key => Object.assign({}, fields.find(field => field.key === "input:" + key), {key: key}));
    }
    function request(action, token) {
        if (busy) {
            if (["confirm", "revert"].includes(action) && !resolvingTransaction) {
                resolvingTransaction = true;
                pendingResolution = {action, token};
            }
            return;
        }
        requestInFlight = true;
        worker.operation = action;
        if (["confirm", "revert"].includes(action)) {
            resolvingTransaction = true;
            transactionPollingPaused = false;
        }
        worker.received = false;
        worker.stdinEnabled = action === "preview";
        worker.payload = action === "preview" ? JSON.stringify(draft) : "";
        worker.command = ["python3", Quickshell.shellPath("scripts/hyprland/desktop.py"), action];
        if (token) worker.command = [...worker.command, token];
        failed = false;
        worker.running = true;
    }
    function refresh() {
        if (busy) { refreshPending = true; return; }
        request("snapshot");
    }
    function preview() { request("preview"); }
    function keep() { if (transaction) request("confirm", transaction.token); }
    function revert() { if (transaction) request("revert", transaction.token); }

    Process {
        id: worker
        property string operation: ""
        property string payload: ""
        property bool received: false
        property bool reloadAfter: false
        onStarted: {
            if (operation === "preview") {
                write(payload);
                stdinEnabled = false;
            }
        }
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const result = JSON.parse(text);
                    worker.received = true;
                    const hadTransaction = root.transaction !== null;
                    if (Object.prototype.hasOwnProperty.call(result, "transaction")) root.transaction = result.transaction;
                    root.now = Date.now();
                    root.failed = !result.ok;
                    if (!result.ok) {
                        root.message = result.error;
                        if (root.transaction) root.transactionPollingPaused = true;
                        else if (hadTransaction) { root.discard(); worker.reloadAfter = true; }
                        return;
                    }
                    if (root.transaction?.phase === "restore_failed") {
                        root.failed = true;
                        root.message = root.transaction.error || "Previous settings could not be restored. Retry manually.";
                        root.transactionPollingPaused = true;
                    }
                    if (worker.operation === "snapshot") {
                        root.monitors = result.monitors;
                        root.devices = result.devices;
                        root.fields = result.fields;
                        root.values = result.values;
                        root.supported = result.supported;
                        root.saved = result.saved;
                        root.integrated = result.integrated;
                        root.loaded = true;
                    } else if (worker.operation === "preview") {
                        root.message = "Preview active. Confirm to keep these settings.";
                    } else if (["confirm", "revert"].includes(worker.operation)) {
                        root.transaction = null;
                        root.message = worker.operation === "confirm" ? "Changes saved." : "Previous settings restored.";
                        root.discard();
                        worker.reloadAfter = true;
                    } else if (worker.operation === "transaction" && !result.transaction && hadTransaction) {
                        root.message = "Preview ended. Previous settings restored.";
                        root.discard();
                        worker.reloadAfter = true;
                    } else if (worker.operation === "install") {
                        root.message = "Desktop integration enabled. Your existing configuration was backed up.";
                        worker.reloadAfter = true;
                    }
                } catch (error) {
                    root.failed = true;
                    if (root.transaction) root.transactionPollingPaused = true;
                    root.message = "Could not read Hyprland settings: " + error;
                }
            }
        }
        stderr: StdioCollector { onStreamFinished: { if (text.trim()) console.warn("[Desktop settings]", text); } }
        onExited: (exitCode, exitStatus) => {
            root.requestInFlight = false;
            if (root.pendingResolution) {
                const pending = root.pendingResolution;
                root.pendingResolution = null;
                Qt.callLater(() => root.request(pending.action, pending.token));
                return;
            }
            root.resolvingTransaction = false;
            if (!received) {
                root.failed = true;
                if (root.transaction) root.transactionPollingPaused = true;
                root.message = "Could not start the settings helper. Check Python and hyprctl.";
            }
            if (reloadAfter || root.refreshPending) {
                reloadAfter = false;
                root.refreshPending = false;
                Qt.callLater(root.refresh);
            }
        }
    }

    Timer {
        interval: 250
        repeat: true
        running: root.transaction !== null && !root.restorationFailed && !root.resolvingTransaction
        onTriggered: {
            root.now = Date.now();
            if (!root.busy && root.now - root.lastTransactionPoll >= 1000) {
                root.lastTransactionPoll = root.now;
                root.request("transaction");
            }
        }
    }
    Timer { id: refreshDelay; interval: 300; onTriggered: { if (!root.changes && !root.transaction && !root.busy) root.refresh(); } }
    Connections {
        target: Hyprland
        function onRawEvent(event) { if (event.name.startsWith("monitor")) refreshDelay.restart(); }
    }
}
