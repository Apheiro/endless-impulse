pragma Singleton
pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland
import qs.modules.shared

Singleton {
    id: root
    property bool enabled: false
    property bool pending: false
    readonly property bool xray: Config.options.appearance.transparency.xray

    // Named rules merge on redeclaration instead of accumulating on every toggle.
    // Keep the tooltip exception after the shell-wide override. QML owns bar
    // and sidebar motion; compositor resize animations would move their contents.
    function rules(value) {
        return 'hl.layer_rule({name="artificial-impulse-xray",match={namespace="^quickshell:.*$"},xray=' + (value ? 'true' : 'false') + '});'
            + 'hl.layer_rule({name="artificial-impulse-tooltip-xray",match={namespace="^quickshell:popup$"},xray=false});'
            + 'hl.layer_rule({name="artificial-impulse-sidebar-animation",match={namespace="^quickshell:sidebar(Right|Left)$"},no_anim=true});'
            + 'hl.layer_rule({name="artificial-impulse-bar-animation",match={namespace="^quickshell:bar$"},no_anim=true})';
    }
    function load() { enabled = true; schedule(); }
    function schedule() { if (enabled && Config.ready) debounce.restart(); }
    onXrayChanged: schedule()
    Connections {
        target: Config
        function onReadyChanged() { root.schedule(); }
    }
    Connections {
        target: Hyprland
        function onRawEvent(event) { if (event.name === "configreloaded") root.schedule(); }
    }
    Timer {
        id: debounce
        interval: 80
        onTriggered: {
            if (worker.running) { root.pending = true; return; }
            root.pending = false;
            worker.command = ["hyprctl", "-r", "eval", root.rules(root.xray)];
            worker.running = true;
        }
    }
    Process {
        id: worker
        stdout: StdioCollector { onStreamFinished: if (text.trim() && text.trim() !== "ok") console.warn("[Layer effects]", text.trim()); }
        stderr: StdioCollector { onStreamFinished: if (text.trim()) console.warn("[Layer effects]", text.trim()); }
        onExited: if (root.pending) root.schedule()
    }
}
