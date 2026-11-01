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
    property var animations: []
    property string error: ""
    readonly property var durations: Config.options.appearance.compositorAnimationDurations
    onDurationsChanged: schedule()
    function refresh() { if (!reader.running) reader.running = true; }
    function setDuration(name, value) {
        const next = Object.assign({}, durations);
        if (value === null) delete next[name];
        else next[name] = value;
        Config.options.appearance.compositorAnimationDurations = next;
    }
    readonly property real speed: Appearance.animationSpeed

    // Only the main shell owns synchronization, not every Settings/test instance.
    function load() { enabled = true; schedule(); }
    function schedule() {
        if (enabled && Config.ready) debounce.restart();
    }
    onSpeedChanged: schedule()
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
            worker.command = ["python3", Quickshell.shellPath("scripts/hyprland/animation_speed.py"), String(root.speed), JSON.stringify(root.durations)];
            worker.running = true;
        }
    }
    Process {
        id: reader
        command: ["python3", Quickshell.shellPath("scripts/hyprland/animation_speed.py"), "--list"]
        stdout: StdioCollector { onStreamFinished: { try { root.animations = JSON.parse(text).animations; root.error = ""; } catch (error) { root.error = "Could not read compositor animations."; } } }
        stderr: StdioCollector { onStreamFinished: if (text.trim()) root.error = text.trim(); }
    }
    Process {
        id: worker
        stdout: StdioCollector { onStreamFinished: { try { root.animations = JSON.parse(text).animations; } catch (error) { console.warn("[Animation speed]", "Could not read timing response"); } } }
        stderr: StdioCollector { onStreamFinished: if (text.trim()) console.warn("[Animation speed]", text.trim()); }
        onExited: if (root.pending) root.schedule()
    }
}
