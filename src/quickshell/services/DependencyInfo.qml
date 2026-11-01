pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root
    property var catalog: ({groups: [], total: 0, sources: []})
    property string error: ""
    readonly property bool busy: reader.running
    readonly property var groups: catalog.groups || []
    function refresh() { if (!reader.running) reader.running = true; }
    Process {
        id: reader
        command: ["python3", Quickshell.shellPath("scripts/system/dependencies.py")]
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const parsed = JSON.parse(text);
                    if (parsed.schema !== 1 || !Array.isArray(parsed.groups)) throw new Error("Invalid map format");
                    root.catalog = parsed;
                    root.error = "";
                } catch (error) { root.error = "Could not read dependency map: " + error; }
            }
        }
        stderr: StdioCollector { id: diagnostics }
        onExited: (code) => { if (code !== 0) root.error = diagnostics.text.trim() || "Could not load dependency map"; }
    }
}
