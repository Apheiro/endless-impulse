pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root
    property string section: ""
    function open(page, detail) { section = page + (detail ? "/" + detail : ""); launcher.running = true; }
    Process {
        id: launcher
        command: ["python3", Quickshell.shellPath("scripts/shell/control.py"), "settings", root.section]
    }
}
