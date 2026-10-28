pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import qs.modules.common

Singleton {
    id: root
    property string theme: ""
    property var themes: []
    property var icons: ({})
    property var aliases: ({})
    property var applications: []
    property var overrides: ({})
    property var paths: []
    property var colorPaths: []
    property string previewTheme: ""
    property var previewIcons: ({})
    property string message: ""
    property bool failed: false
    property bool loaded: false
    property bool pending: false
    readonly property bool busy: worker.running

    function iconPath(name, fallback) {
        if (typeof fallback === "boolean") return icons[name] || Quickshell.iconPath(name, fallback);
        if (!name) name = fallback || "image-missing";
        const replacement = icons[name];
        if (replacement) return replacement;
        if (name.startsWith("/") || name.startsWith("file:") || name.startsWith("image:") || name.startsWith("data:")) return name;
        return Quickshell.iconPath(name, fallback || "image-missing");
    }
    function refresh() {
        if (busy) { pending = true; return; }
        request("snapshot", {});
    }
    function preview(theme) {
        if (!busy) request("preview", {theme: theme});
    }
    function apply(payload) { if (!busy) request("apply", payload); }
    function request(action, payload) {
        worker.payload = JSON.stringify(payload);
        worker.stdinEnabled = action !== "snapshot";
        worker.command = ["python3", Quickshell.shellPath("scripts/icons/themes.py"), action];
        worker.received = false;
        failed = false;
        worker.running = true;
    }
    Component.onCompleted: refresh()
    FileView {
        path: Directories.shellConfig + "/icons.json"
        watchChanges: true
        onFileChanged: refreshTimer.restart()
    }
    Timer { id: refreshTimer; interval: 200; onTriggered: root.refresh() }
    Process {
        id: worker
        property string payload: ""
        property bool received: false
        onStarted: {
            if (stdinEnabled) { write(payload); stdinEnabled = false; }
        }
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const result = JSON.parse(text);
                    worker.received = true;
                    if (!result.ok) { root.failed = true; root.message = result.error; return; }
                    if (result.previewTheme) {
                        root.previewTheme = result.previewTheme;
                        root.previewIcons = result.previewIcons;
                        return;
                    }
                    root.theme = result.theme;
                    root.themes = result.themes;
                    root.icons = result.icons;
                    root.aliases = result.aliases;
                    root.applications = result.applications;
                    root.overrides = result.overrides;
                    root.paths = result.paths;
                    root.colorPaths = result.colorPaths;
                    root.loaded = true;
                    if (result.message) root.message = [result.message, ...(result.warnings || [])].join(" ");
                } catch (error) { root.failed = true; root.message = "Could not read icon settings: " + error; }
            }
        }
        onExited: (code, status) => {
            if (!received) { root.failed = true; root.message = "Could not start the icon settings helper."; }
            if (root.pending) { root.pending = false; Qt.callLater(root.refresh); }
        }
    }
}
