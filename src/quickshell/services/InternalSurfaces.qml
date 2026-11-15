pragma Singleton
pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland
import qs.modules.shared

Singleton {
    id: root
    readonly property string workspace: "special:endless-internal"
    property bool loaded: false
    property bool pending: false
    property string error: ""
    readonly property bool busy: worker.running || refresh.running || pending
    readonly property string preferences: JSON.stringify({
        xembedEnabled: Config.options.internalSurfaces.xembedEnabled,
        rules: Config.options.internalSurfaces.rules
    })
    property var entries: [{id: "xembed", windowClass: "xembedsniproxy", title: "",
        purpose: "XEmbed → StatusNotifier", enabled: Config.options.internalSurfaces.xembedEnabled, builtin: true}]

    function load() { loaded = true; schedule(); }
    function schedule() {
        if (!loaded || !Config.ready) return;
        if (worker.running) { pending = true; return; }
        // First-event bounded coalescing: an event burst cannot starve this query.
        if (!refresh.running) refresh.start();
    }
    function retry() { error = ""; schedule(); }
    function run(action, config) {
        worker.action = action;
        worker.config = config;
        worker.received = false;
        worker.command = ["python3", Quickshell.shellPath("scripts/hyprland/internal_surfaces.py"),
            action, "--config", config];
        worker.running = true;
    }
    function edit(manualRules, xembedEnabled) {
        if (busy) return;
        error = "";
        run("validate", JSON.stringify({xembedEnabled: xembedEnabled, rules: manualRules}));
    }
    function setEnabled(entry, value) {
        if (entry.builtin) edit(Config.options.internalSurfaces.rules, value);
        else edit(Config.options.internalSurfaces.rules.map(rule =>
            rule.windowClass === entry.windowClass && rule.title === entry.title
                ? Object.assign({}, rule, {enabled: value}) : rule), Config.options.internalSurfaces.xembedEnabled);
    }
    function remove(entry) {
        if (!entry.builtin) edit(Config.options.internalSurfaces.rules.filter(rule =>
            rule.windowClass !== entry.windowClass || rule.title !== entry.title), Config.options.internalSurfaces.xembedEnabled);
    }
    function add(windowClass, title, purpose) {
        edit([...Config.options.internalSurfaces.rules, {windowClass: windowClass.trim(),
            title: title, purpose: purpose.trim(), enabled: true}], Config.options.internalSurfaces.xembedEnabled);
    }
    function matches(entry, client) {
        return client && client.class === entry.windowClass && client.floating
            && (entry.builtin ? client.xwayland : client.title === entry.title);
    }
    function surfaces(entry) { return HyprlandData.windowList.filter(client => matches(entry, client)); }
    function isInternal(toplevel) {
        const client = HyprlandData.clientForToplevel(toplevel);
        if (client?.workspace?.name === workspace) return true;
        // Hide the integrated container during the short client-inventory race too.
        if (Config.options.internalSurfaces.xembedEnabled
                && toplevel?.appId === "xembedsniproxy") return true;
        return entries.some(entry => entry.enabled && matches(entry, client));
    }
    onPreferencesChanged: schedule()
    Connections {
        target: Config
        function onReadyChanged() { root.schedule(); }
    }
    Connections {
        target: Hyprland
        function onRawEvent(event) {
            // Own move events only refresh HyprlandData, never trigger another move.
            if (["configreloaded", "openwindow"].includes(event.name)) root.schedule();
        }
    }
    Timer { id: refresh; interval: 180; onTriggered: root.run("apply", root.preferences) }
    Process {
        id: worker
        property string action: ""
        property string config: ""
        property bool received: false
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const result = JSON.parse(text);
                    worker.received = true;
                    root.error = result.ok ? "" : result.error;
                    if (worker.action === "validate" && result.ok) {
                        const config = JSON.parse(worker.config);
                        Config.options.internalSurfaces.xembedEnabled = config.xembedEnabled;
                        Config.options.internalSurfaces.rules = config.rules;
                        root.pending = true;
                    }
                    if (result.entries) root.entries = result.entries;
                    if (result.clients) HyprlandData.applyResult("clients", JSON.stringify(result.clients));
                } catch (error) { root.error = String(error); }
            }
        }
        stderr: StdioCollector { onStreamFinished: if (text.trim()) console.warn("[Internal surfaces]", text.trim()); }
        onExited: {
            if (!received) root.error = "No response from the internal surfaces adapter";
            HyprlandData.updateWindowList();
            if (root.pending) { root.pending = false; root.schedule(); }
        }
    }
}
