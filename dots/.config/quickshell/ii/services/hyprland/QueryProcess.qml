import QtQuick
import Quickshell.Io

// Separate from the singleton so Qt can resolve it throughout the shell's import graph.
Process {
    id: root
    required property string queryName
    required property int queryFlag
    signal resultReceived(string name, string payload)
    signal finished(string name, int exitCode)

    command: ["hyprctl", queryName, "-j"]
    stdout: StdioCollector {
        onStreamFinished: root.resultReceived(root.queryName, text)
    }
    onExited: (exitCode, exitStatus) => root.finished(queryName, exitCode)
}
