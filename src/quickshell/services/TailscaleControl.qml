pragma Singleton
pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland
import qs
import qs.modules.shared

Singleton {
    id: root
    property bool opened: false
    property string screenName: ""
    property bool ready: false
    property bool loaded: false
    property var state: ({installed: false, running: false, profiles: [], peers: [], prefs: {}, health: [], setFlags: []})
    property var schema: ({path: [], children: [], flags: [], positionals: [], usage: "", description: ""})
    property var commandPath: []
    property var requests: ({})
    property var queue: []
    property int sequence: 0
    property bool commandRunning: false
    property string error: ""
    property string output: ""
    readonly property bool busy: commandRunning || Object.values(requests).some(item => item === "run")
    readonly property bool refreshing: Object.values(requests).some(item => item === "refresh")
    readonly property bool schemaLoading: Object.values(requests).some(item => item === "schema")
    function request(action, payload = {}) {
        const id = String(++sequence);
        requests = Object.assign({}, requests, {[id]: action});
        queue = [...queue, Object.assign({id, action}, payload)];
        drain();
    }
    function drain() {
        if (!ready || !worker.running) return;
        const pending = queue; queue = [];
        for (const item of pending) worker.write(JSON.stringify(item) + "\n");
    }
    function refresh() { if (!refreshing) request("refresh"); }
    function open() {
        screenName = Hyprland.focusedMonitor?.name ?? Quickshell.screens[0]?.name ?? "";
        GlobalStates.sidebarRightOpen = false;
        opened = true; refresh();
    }
    function close() { opened = false; }
    function toggle() {
        if (!state.installed || state.backendState === "Unavailable") { open(); return; }
        // A bare up resumes saved preferences. Even --timeout makes up require
        // all non-default settings again (including the existing operator).
        if (!busy) run([state.running ? "down" : "up"]);
    }
    function run(path, flags = {}, args = [], admin = false) {
        if (busy) return;
        error = ""; output = "";
        request("run", {path, flags, args, admin, terminal: Config.options.apps.terminal});
    }
    function setFlag(name, value) { run(["set"], {[name]: value}); }
    function switchTo(profile) { run(["switch"], {}, [profile.id]); }
    signal operationCompleted(bool success)
    function selectCommand(path) { commandPath = path; request("schema", {path}); }
    function openURL(url) { if (/^https:\/\//i.test(url)) Qt.openUrlExternally(url); }
    Timer { interval: root.opened ? 3000 : 15000; running: root.ready; repeat: true; onTriggered: root.refresh() }
    Process {
        id: worker
        running: true
        stdinEnabled: true
        command: ["python3", Quickshell.shellPath("scripts/tailscale/control.py")]
        onStarted: { root.ready = true; root.drain(); root.refresh(); }
        stdout: SplitParser {
            onRead: line => {
                try {
                    const data = JSON.parse(line);
                    if (data.event === "state") { root.state = data.state; root.loaded = true; }
                    else if (data.event === "schema" && JSON.stringify(data.schema.path) === JSON.stringify(root.commandPath)) root.schema = data.schema;
                    else if (data.event === "running") root.commandRunning = data.value;
                    else if (data.event === "output") root.output = (root.output + data.text).slice(-100000);
                    else if (data.event === "result") {
                        const operation = root.requests[data.id];
                        const next = Object.assign({}, root.requests); delete next[data.id]; root.requests = next;
                        if (!data.ok) root.error = data.error;
                        if (operation === "run") root.operationCompleted(data.ok);
                    } else if (data.event === "error") root.error = data.error;
                } catch (error) { root.error = "Could not read the Tailscale service response."; }
            }
        }
        onExited: { root.ready = false; root.requests = {}; root.commandRunning = false; root.error = "Tailscale integration stopped. Reload the shell to reconnect."; }
    }
    Connections { target: GlobalStates; function onScreenLockedChanged() { if (GlobalStates.screenLocked) root.close(); } }
    IpcHandler {
        target: "tailscale"
        function open(): void { root.open(); }
        function close(): void { root.close(); }
        function status(): string { return JSON.stringify({loaded: root.loaded, installed: root.state.installed, running: root.state.running, profiles: root.state.profiles.length, busy: root.busy}); }
    }
}
