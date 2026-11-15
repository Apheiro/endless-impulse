pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import qs.modules.shared

Singleton {
    id: root
    property var settings: ({defaultTarget: "region", saveDirectory: ""})
    property var capabilities: ({installed: false, codecs: [], capture: [], audio: [], applications: [], cameras: []})
    property var fields: []
    property var state: ({active: false, phase: "idle"})
    property string preview: ""
    property string message: ""
    property string store: Directories.shellConfig + "/recorder.json"
    property string statePath: (Quickshell.env("XDG_STATE_HOME") || Directories.home.replace(/^file:\/\//, "") + "/.local/state") + "/endless-Impulse/recorder"
    property bool loaded: false
    property bool preferencesExist: false
    property bool failed: false
    property bool refreshPending: false
    property bool stopPending: false
    property double lastStatusAt: Date.now()
    property double now: Date.now()
    readonly property bool busy: worker.running
    readonly property bool active: !!state.active
    readonly property bool recording: active && state.phase === "recording"
    readonly property bool paused: !!state.paused
    readonly property int elapsed: Math.max(0, Math.floor((state.elapsed || 0) + (recording && !paused ? (now - lastStatusAt) / 1000 : 0)))
    readonly property string elapsedText: {
        const seconds = elapsed % 60;
        const minutes = Math.floor(elapsed / 60) % 60;
        const hours = Math.floor(elapsed / 3600);
        return (hours ? String(hours).padStart(2, "0") + ":" : "") + String(minutes).padStart(2, "0") + ":" + String(seconds).padStart(2, "0");
    }
    property var pendingRegion: ({})
    signal preferencesSaved()

    function request(action, payload) {
        if (busy) { if (action === "status" || action === "snapshot") refreshPending = true; return; }
        worker.operation = action;
        worker.payload = payload === undefined ? "" : JSON.stringify(payload);
        worker.stdinEnabled = payload !== undefined;
        worker.command = ["python3", Quickshell.shellPath("scripts/videos/recorder.py"), action];
        worker.received = false;
        failed = false;
        worker.running = true;
    }
    function refresh() { request("snapshot"); }
    function start(target, monitor, withSound) {
        if (active || busy) return;
        if ((target || settings.defaultTarget) === "region" && settings.mode !== "audio") {
            Quickshell.execDetached(["python3", Quickshell.shellPath("scripts/shell/control.py"), "ipc", "region", withSound ? "recordWithSound" : "record"]);
            return;
        }
        request("start", {target: target || settings.defaultTarget, monitor: monitor || "", sound: !!withSound});
    }
    function startRegion(region, withSound) {
        pendingRegion = {target: "region", region: region, sound: !!withSound};
        regionStart.restart();
    }
    Timer { id: regionStart; interval: 120; onTriggered: root.request("start", root.pendingRegion) }
    IpcHandler {
        target: "recording"
        function refresh() { root.refresh(); }
        function stop() { root.stop(); }
        function pause() { root.pause(); }
        function saveReplay() { root.saveReplay(); }
        function fullscreen() { root.start("fullscreen"); }
    }
    function stop() { if (busy) stopPending = true; else request("stop"); }
    function toggle() { if (active) stop(); else start(); }
    function pause() { request("pause"); }
    function saveReplay() { request("save-replay"); }
    function parallel() { request("parallel"); }
    function save(values) { request("save", values); }
    function previewName(values) { request("preview", values); }
    Component.onCompleted: refresh()
    Timer { interval: 250; running: root.active; repeat: true; onTriggered: root.now = Date.now() }
    Timer { interval: 2000; running: root.active; repeat: true; onTriggered: root.request("status") }
    FileView { id: sessionFile; path: root.statePath + "/session.json"; watchChanges: true; onFileChanged: stateRefresh.restart() }
    FileView { path: root.store; watchChanges: true; onFileChanged: settingsRefresh.restart() }
    Timer { id: stateRefresh; interval: 80; onTriggered: root.request("status") }
    Timer { id: settingsRefresh; interval: 100; onTriggered: root.refresh() }
    Process {
        id: worker
        property string operation: ""
        property string payload: ""
        property bool received: false
        onStarted: { if (stdinEnabled) { write(payload); stdinEnabled = false; } }
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const result = JSON.parse(text);
                    worker.received = true;
                    if (!result.ok) { root.failed = true; root.message = result.error; return; }
                    if (result.settings) root.settings = result.settings;
                    if (result.storeExists !== undefined) root.preferencesExist = result.storeExists;
                    if (result.capabilities) { root.capabilities = result.capabilities; root.fields = result.fields; root.store = result.store; root.statePath = result.statePath; root.loaded = true; sessionFile.watchChanges = false; sessionFile.reload(); sessionFile.watchChanges = true; }
                    if (result.preview) root.preview = result.preview;
                    if (result.status) {
                        root.lastStatusAt = Date.now(); root.now = root.lastStatusAt;
                        root.state = result.status;
                        if (result.status.error) { root.failed = true; root.message = result.status.error; }
                    }
                    if (result.message) root.message = result.message;
                    if (worker.operation === "save") root.preferencesSaved();
                } catch (error) { root.failed = true; root.message = "Could not read recording status: " + error; }
            }
        }
        stderr: StdioCollector { onStreamFinished: { if (text.trim()) console.warn("[Recorder]", text); } }
        onExited: (code, status) => {
            if (!received) { root.failed = true; root.message = "Could not start the recording helper."; }
            if (root.stopPending) { root.stopPending = false; Qt.callLater(root.stop); return; }
            if (root.refreshPending) { root.refreshPending = false; Qt.callLater(root.refresh); }
        }
    }
}
