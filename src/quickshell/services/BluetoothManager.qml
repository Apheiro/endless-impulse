pragma Singleton
pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland
import Quickshell.Bluetooth
import qs

Singleton {
    id: root
    property bool opened: false
    property string screenName: ""
    property string selectedAdapterPath: ""
    readonly property var adapters: Bluetooth.adapters.values
    readonly property var adapter: adapters.find(item => item.dbusPath === selectedAdapterPath)
                                   || Bluetooth.defaultAdapter || null
    readonly property var devices: adapter?.devices.values || []
    property bool agentReady: false
    property bool backendEnabled: true
    property string message: ""
    property bool failed: false
    property var prompt: ({})
    property var operations: ({})
    property var queue: []
    property int sequence: 0
    property var scanOwner: null
    property var visibleOwner: null
    property var visiblePrevious: ({})
    readonly property bool receiving: visibleOwner !== null
    signal operationCompleted(string action, bool success)

    function open(name) {
        screenName = name || Hyprland.focusedMonitor?.name || Quickshell.screens[0]?.name || "";
        failed = false;
        message = "";
        opened = true;
        backendEnabled = true;
        QuickPanelState.activate("bluetooth");
        GlobalStates.sidebarRightOpen = false;
    }
    function close() {
        QuickPanelState.deactivate("bluetooth");
        for (const operation of Object.values(operations))
            if (operation.action === "pair" && agentReady)
                command("cancel", operation.device);
        if (prompt.id) {
            if (prompt.kind.startsWith("Display"))
                command("cancel", prompt.device);
            else
                respond(false, "");
        }
        stopScan();
        stopReceiving();
        opened = false;
    }
    function stopScan() {
        scanTimer.stop();
        if (scanOwner)
            scanOwner.discovering = false;
        scanOwner = null;
    }
    function scan() {
        if (!adapter?.enabled)
            return;
        if (scanOwner || adapter.discovering) {
            stopScan();
            return;
        }
        scanOwner = adapter;
        adapter.discovering = true;
        scanTimer.restart();
    }
    function changeAdapter(path) {
        stopScan();
        stopReceiving();
        selectedAdapterPath = path;
    }
    function setPowered(value) {
        if (!adapter)
            return;
        if (!value) {
            stopScan();
            stopReceiving();
        }
        adapter.enabled = value;
    }
    function receive() {
        if (receiving) {
            stopReceiving();
            return;
        }
        if (!adapter?.enabled || !agentReady)
            return;
        command("incoming", "", {
                    enable: true,
                    adapter: adapter.dbusPath
                });
    }
    function stopReceiving() {
        receiveTimer.stop();
        if (!visibleOwner)
            return;
        visibleOwner.discoverable = visiblePrevious.discoverable;
        visibleOwner.pairable = visiblePrevious.pairable;
        visibleOwner.discoverableTimeout = visiblePrevious.timeout;
        visibleOwner = null;

    }
    function pairing(path) { return Object.values(operations).some(item => item.device === path && item.action === "pair"); }
    function actionFor(path) { return Object.values(operations).find(item => item.device === path)?.action || ""; }
    function pending(path) {
        return Object.values(operations).some(item => item.device === path);
    }
    function command(action, device, extra) {
        const payload = Object.assign({
                                          id: String(++sequence),
                                          action: action,
                                          device: device || ""
                                      }, extra || {});
        operations = Object.assign({}, operations, {
                                       [payload.id]: payload
                                   });
        queue = [...queue, payload];
        backendEnabled = true;
        drain();
    }
    function respond(accept, value) {
        command("respond", "", {
                    prompt: prompt.id,
                    accept: accept,
                    value: value
                });
    }
    function drain() {
        if (!agentReady || !backend.running)
            return;
        const commands = queue;
        queue = [];
        for (const payload of commands)
            backend.write(JSON.stringify(payload) + "\n");
    }
    function retry() {
        backendEnabled = false;
        retryTimer.restart();
    }
    function nameFor(path) {
        return Bluetooth.devices.values.find(item => item.dbusPath === path)?.name || path.split("/").pop().replace(/^dev_/,
                                                                                                                    "").replace(
                    /_/g, ":");
    }
    onAdaptersChanged: {
        if (scanOwner && !adapters.includes(scanOwner)) { scanOwner=null;scanTimer.stop(); }
        if (visibleOwner && !adapters.includes(visibleOwner)) { visibleOwner=null;receiveTimer.stop(); }
        if (opened && !backend.running)
            retry();
    }
    Timer {
        id: retryTimer
        interval: 250
        onTriggered: root.backendEnabled = true
    }
    Timer {
        id: scanTimer
        interval: 30000
        onTriggered: root.stopScan()
    }
    Timer {
        id: receiveTimer
        interval: 180000
        onTriggered: root.stopReceiving()
    }
    Connections {
        target: root.adapter
        function onEnabledChanged() {
            if (!root.adapter?.enabled) { root.stopScan(); root.stopReceiving(); }
        }
    }
    Connections {
        target: GlobalStates
        function onScreenLockedChanged() {
            if (GlobalStates.screenLocked)
                root.close();
        }
    }
    Process {
        id: backend
        running: root.backendEnabled && (root.opened || Object.keys(root.operations).length > 0)
        stdinEnabled: true
        command: ["python3", Quickshell.shellPath("scripts/bluetooth/agent.py")]
        stdout: SplitParser {
            onRead: line => {
                try {
                    const data = JSON.parse(line);
                    if (data.event === "ready") {
                        root.agentReady = data.ok;
                        root.failed = !data.ok;
                        root.message = data.error || "";
                        if (data.ok)
                            root.drain();
                        else {
                            root.queue = [];
                            root.operations = {};
                        }
                    } else if (data.event === "prompt") {
                        root.prompt = data.prompt;
                        if (root.prompt.id && (GlobalStates.screenLocked || !root.opened)) {
                            if (root.prompt.kind.startsWith("Display"))
                                root.command("cancel", root.prompt.device);
                            else
                                root.respond(false, "");
                        }
                    } else if (data.event === "notice") {
                        root.failed = true;
                        root.message = data.error;
                    } else if (data.event === "result") {
                        const operation = root.operations[data.id];
                        const next = Object.assign({}, root.operations);
                        delete next[data.id];
                        root.operations = next;
                        root.failed = !data.ok;
                        root.message = data.error || "";
                        if (operation?.action === "incoming" && operation.enable && data.ok && root.opened) {
                            const target = root.adapters.find(item => item.dbusPath === operation.adapter);
                            if (target?.enabled) {
                                root.visiblePrevious = {
                                    discoverable: target.discoverable,
                                    pairable: target.pairable,
                                    timeout: target.discoverableTimeout
                                };
                                root.visibleOwner = target;
                                target.discoverableTimeout = 180;
                                target.pairable = true;
                                target.discoverable = true;
                                receiveTimer.restart();
                            }
                        }
                        if (operation)
                            root.operationCompleted(operation.action, data.ok);
                    }
                } catch (error) {
                    root.failed = true;
                    root.message = "Could not read Bluetooth response: " + error;
                }
            }
        }
        stderr: StdioCollector {
            id: helperError
        }
        onExited: {
            if (root.opened && root.backendEnabled) {
                root.failed = true;
                root.message = helperError.text || "Bluetooth agent unavailable. Retry to reconnect.";
            }
            root.agentReady = false;
            root.prompt = {};
            root.queue = [];
            if (Object.keys(root.operations).length) {
                root.operations = {};
                root.failed = true;
                root.message = "Bluetooth operation interrupted. Please retry.";
            }
        }
    }
    IpcHandler {
        target: "bluetooth"
        function open() {
            root.open();
        }
        function close() {
            root.close();
        }
        function toggle() {
            if (root.opened)
                root.close();
            else
                root.open();
        }
    }
}
