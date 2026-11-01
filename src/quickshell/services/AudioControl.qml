pragma Singleton
pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland
import Quickshell.Services.Pipewire
import qs
import qs.modules.shared

Singleton {
    id: root
    property bool opened: false
    property string screenName: ""
    property string section: "playback"
    property bool loaded: false
    property bool failed: false
    property string message: ""
    property string errorOperation: ""
    property bool boost: false
    property bool inputMeters: false
    property bool showMonitors: false
    property var server: ({})
    property var clock: ({})
    property var ports: []
    property var graphObjects: []
    property var queue: []
    property var pendingVolumes: ({})
    property int volumeRevision: 0
    readonly property bool refreshing: busy || activityHold.running
    onBusyChanged: {
        if (busy)
            activityHold.restart();
    }
    Timer {
        id: activityHold
        interval: 1400
    }
    property bool refreshPending: false
    readonly property bool busy: worker.running
    property ListModel outputs: ListModel {
        dynamicRoles: true
    }
    property ListModel inputs: ListModel {
        dynamicRoles: true
    }
    property ListModel playback: ListModel {
        dynamicRoles: true
    }
    property ListModel recording: ListModel {
        dynamicRoles: true
    }
    property ListModel cards: ListModel {
        dynamicRoles: true
    }
    property ListModel links: ListModel {
        dynamicRoles: true
    }

    function open(name, page) {
        screenName = name || Hyprland.focusedMonitor?.name || Quickshell.screens[0]?.name || "";
        if (page)
            section = page;
        opened = true;
        QuickPanelState.activate("audio");
        GlobalStates.sidebarRightOpen = false;
        refresh();
    }
    function toggle(name) {
        if (opened && (!name || screenName === name))
            close();
        else
            open(name);
    }
    function close() {
        QuickPanelState.deactivate("audio");
        opened = false;
        inputMeters = false;
    }
    function entries(model) {
        return Array.from({
                              length: model.count
                          }, (_, index) => model.get(index).entry);
    }
    function deviceLabel(entry, direct) {
        if (entry.processor === "easyeffects") {
            const destinations = entry.routeDevices.map(device => device.name).join(" + ");
            if (!destinations)
                return "EasyEffects · " + Translation.tr("No connected device");
            return entry.kind === "sink" ? "EasyEffects → " + destinations : destinations + " → EasyEffects";
        }
        return entry.name + (direct ? " · " + Translation.tr("Direct") : "");
    }
    function sync(model, rows) {
        const ids = rows.map(row => row.id + ":" + row.serial);
        for (let i = model.count - 1; i >= 0; i--)
            if (!ids.includes(model.get(i).entry.id + ":" + model.get(i).entry.serial))
                model.remove(i);
        rows.forEach((row, index) => {
            const key = row.id + ":" + row.serial;
            let existing = -1;
            for (let i = index; i < model.count; i++)
                if (model.get(i).entry.id + ":" + model.get(i).entry.serial === key) {
                    existing = i;
                    break;
                }
            if (existing < 0)
                model.insert(index, {
                                 entry: row
                             });
            else {
                if (existing !== index)
                    model.move(existing, index, 1);
                model.setProperty(index, "entry", row);
            }
        });
    }
    function refresh() {
        if (busy || queue.length) {
            refreshPending = true;
            return;
        }
        launch("snapshot");
    }
    function volumeKey(entry) {
        return entry.kind + ":" + entry.id + ":" + entry.serial;
    }
    function previewVolume(entry, channel) {
        const pending = pendingVolumes[volumeKey(entry)];
        if (pending) {
            if (pending.values)
                return channel >= 0 ? pending.values[channel] : Math.max(...pending.values);
            return pending.value;
        }
        return channel >= 0 ? entry.channels[channel].volume : entry.volume;
    }
    function rememberVolume(action) {
        action.revision = ++volumeRevision;
        pendingVolumes = Object.assign({}, pendingVolumes, {
                                           [volumeKey(action)]: Object.assign({}, action, {
                                                                                  acknowledged: false,
                                                                                  expires: Date.now() + 8000
                                                                              })
                                       });
    }
    function acknowledgeVolume(action, success) {
        const key = volumeKey(action), pending = pendingVolumes[key];
        if (!pending || pending.revision !== action.revision)
            return;
        const next = Object.assign({}, pendingVolumes);
        if (success)
            next[key] = Object.assign({}, pending, {
                                          acknowledged: true
                                      });
        else
            delete next[key];
        pendingVolumes = next;
    }
    function reconcileVolumes(result, revision) {
        const next = Object.assign({}, pendingVolumes);
        let changed = false;
        for (const [key, pending] of Object.entries(next)) {
            const entry = (result[pending.kind] || []).find(item => volumeKey(item) === key);
            const confirmed = entry && pending.acknowledged && revision >= pending.revision && (
                      pending.values ? pending.values.every((value, index) => Math.abs(value
                                                                                       - entry.channels[index]
                                                                                       ?.volume) < 1) :
                                       entry.channels.every(channel => Math.abs(channel.volume
                                                                                - pending.value) < 1));
            if (confirmed || !entry || Date.now() >= pending.expires) {
                delete next[key];
                changed = true;
            }
        }
        if (changed)
            pendingVolumes = next;
    }
    function defaultOutputVolume(fallback) {
        const entry = entries(outputs).find(item => item.technicalName === Pipewire.defaultAudioSink?.name);
        const pending = entry && pendingVolumes[volumeKey(entry)];
        return pending ? previewVolume(entry, -1) / 100 : fallback;
    }
    function adjustDefaultVolume(direction) {
        const limit = Config.options.audio.protection.enable ? Math.min(100,
                                                                        Config.options.audio.protection.maxAllowed) :
                                                               100;
        const node = Pipewire.defaultAudioSink;
        const entry = entries(outputs).find(item => item.technicalName === node?.name);
        if (entry && node?.ready && entry.pwId === node.id
            && (!node.properties["object.serial"] || String(node.properties["object.serial"]) === entry.serial)) {
            const current = pendingVolumes[volumeKey(entry)] ? previewVolume(entry, -1) : Math.max(
                                                                   ...node.audio.volumes) * 100;
            const value = Math.max(0, Math.min(limit, current + direction * (current < 10 ? 1 : 2)));
            objectAction("volume", entry, Math.round(value));
        } else {
            perform({
                        action: "adjust-default",
                        steps: direction,
                        limit: limit
                    });
        }
    }
    function perform(action) {
        failed = false;
        message = "";
        if (action.action === "volume")
            rememberVolume(action);
        if (action.action === "adjust-default") {
            const queued = queue.find(item => item.payload.action === "adjust-default");
            if (queued)
                action.steps += queued.payload.steps;
        }
        const key = action.action + ":" + (action.kind || "") + ":" + (action.id || "") + ":" + (action.key
                                                                                                 || "");
        const next = queue.filter(item => item.key !== key);
        next.push({
                      key: key,
                      payload: action
                  });
        queue = next;
        dispatch.restart();
    }
    function objectAction(action, entry, value) {
        perform({
                    action: action,
                    kind: entry.kind,
                    id: entry.id,
                    serial: entry.serial,
                    value: value
                });
    }
    function drain() {
        if (busy)
            return;
        if (queue.length) {
            const next = [...queue];
            const item = next.shift();
            queue = next;
            launch("action", item.payload);
        } else if (refreshPending) {
            refreshPending = false;
            refresh();
        }
    }
    function launch(operation, payload) {
        worker.snapshotRevision = volumeRevision;
        worker.request = payload || {};
        worker.operation = operation;
        worker.payload = JSON.stringify(payload || {});
        worker.received = false;
        worker.stdinEnabled = operation === "action";
        worker.command = ["python3", Quickshell.shellPath("scripts/audio/control.py"), operation];
        worker.running = true;
    }
    Timer {
        id: dispatch
        interval: 70
        onTriggered: root.drain()
    }
    Timer {
        id: refreshDelay
        interval: 180
        onTriggered: root.refresh()
    }
    Timer {
        interval: 4000
        running: root.opened
        repeat: true
        onTriggered: root.refresh()
    }
    Connections {
        target: GlobalStates
        function onScreenLockedChanged() {
            if (GlobalStates.screenLocked)
                root.close();
        }
    }
    Process {
        command: ["pactl", "subscribe"]
        running: root.opened
        stdout: SplitParser {
            onRead: line => {
                if (/ on (sink|source|sink-input|source-output|card|server)( #|$)/.test(line))
                    refreshDelay.restart();
            }
        }
    }
    Process {
        id: worker
        property string operation: ""
        property string payload: ""
        property bool received: false
        property int snapshotRevision: 0
        property var request: ({})
        onStarted: {
            if (stdinEnabled) {
                write(payload);
                stdinEnabled = false;
            }
        }
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const result = JSON.parse(text);
                    worker.received = true;
                    if (worker.operation === "action" && worker.request.action === "volume")
                        root.acknowledgeVolume(worker.request, result.ok);
                    if (!result.ok) {
                        if (worker.operation === "action") root.refreshPending = true;
                        root.failed = true;
                        root.errorOperation = worker.operation;
                        root.message = result.error;
                        return;
                    }
                    if (worker.operation === "action" || root.errorOperation === "snapshot") {
                        root.failed = false;
                        root.message = "";
                    }
                    if (worker.operation === "snapshot") {
                        root.sync(root.outputs, result.sink);
                        root.sync(root.inputs, result.source);
                        root.sync(root.playback, result["sink-input"]);
                        root.sync(root.recording, result["source-output"]);
                        root.sync(root.cards, result.cards);
                        root.sync(root.links, result.links);
                        root.ports = result.ports;
                        root.graphObjects = result.objects;
                        root.server = result.server;
                        root.clock = result.clock;
                        root.reconcileVolumes(result, worker.snapshotRevision);
                        root.loaded = true;
                    } else {
                        root.refreshPending = true;
                        root.message = "";
                    }
                } catch (error) {
                    root.failed = true;
                    root.message = "Could not read audio state: " + error;
                }
            }
        }
        onExited: (code, status) => {
            if (!received) {
                if (worker.operation === "action" && worker.request.action === "volume")
                    root.acknowledgeVolume(worker.request, false);
                root.failed = true;
                root.message = "Could not start the audio helper.";
            }
            Qt.callLater(root.drain);
        }
    }
    IpcHandler {
        target: "audio"
        function toggle() {
            root.toggle();
        }
        function open() {
            root.open();
        }
        function close() {
            root.close();
        }
    }
}
