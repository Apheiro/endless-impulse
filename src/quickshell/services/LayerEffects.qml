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
    // XEmbed's mapped 32px capture containers must remain alive for tray icons.
    // Hyprland needs an explicit rule instead of their X11 opacity hint.
    function rules(value) {
        return 'hl.layer_rule({name="endless-Impulse-xray",match={namespace="^quickshell:.*$"},xray=' + (value ? 'true' : 'false') + '});'
            + 'hl.layer_rule({name="endless-Impulse-tooltip-xray",match={namespace="^quickshell:popup$"},xray=false});'
            + 'hl.layer_rule({name="endless-Impulse-sidebar-animation",match={namespace="^quickshell:sidebar(Right|Left)$"},no_anim=true});'
            + 'hl.layer_rule({name="endless-Impulse-bar-animation",match={namespace="^quickshell:bar$"},no_anim=true});'
            + 'hl.window_rule({name="endless-Impulse-xembed-proxy",match={class="^xembedsniproxy$"},opacity="0 override",no_blur=true,no_shadow=true,border_size=0,no_focus=true,no_initial_focus=true})';
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
