pragma Singleton
pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Wayland
import Quickshell.Hyprland
import qs

Singleton {
    id: root
    readonly property int limit: 24
    property var frames: ({})
    property var hosts: []
    property var queue: []
    property var current: null
    property var order: []

    function key(toplevel) {
        const address = toplevel?.HyprlandToplevel?.address;
        if (!address) return "";
        const id = String(address).startsWith("0x") ? String(address) : "0x" + address;
        return /^0x0+$/.test(id) ? "" : id;
    }
    function frame(toplevel) {
        const entry = frames[key(toplevel)];
        return entry?.toplevel === toplevel ? entry : null;
    }
    function image(toplevel) { return frame(toplevel)?.grab?.url ?? ""; }
    function size(toplevel) {
        const entry = frame(toplevel);
        return entry ? Qt.size(entry.width, entry.height) : Qt.size(200, 120);
    }
    function touch(toplevel) {
        const id = key(toplevel);
        if (frames[id]) order = order.filter(value => value !== id).concat([id]);
    }
    function registerHost(host) { hosts = hosts.concat([host]); }
    function unregisterHost(host) {
        hosts = hosts.filter(value => value !== host);
        host.abort();
    }
    function capture(toplevel, callback, wanted) {
        const id = key(toplevel);
        if (!id || GlobalStates.screenLocked) { if (callback) callback(); return; }
        const cached = frame(toplevel);
        if (cached && Date.now() - cached.requestedAt < 1000) {
            touch(toplevel);
            if (callback) callback();
            return;
        }
        const existing = current?.id === id ? current : queue.find(job => job.id === id);
        const listener = {done: callback, wanted: wanted};
        if (existing) { existing.callbacks.push(listener); return; }
        queue = queue.concat([{id: id, toplevel: toplevel, callbacks: [listener]}]);
        drain();
    }
    function drain() {
        if (current || !queue.length) return;
        const job = queue[0];
        queue = queue.slice(1);
        const host = hosts.find(host => host && host.canCapture);
        if (!host || !job.toplevel || GlobalStates.screenLocked || !job.callbacks.some(listener => !listener.wanted || listener.wanted())) {
            for (const listener of job.callbacks) { if (listener.done) listener.done(); }
            Qt.callLater(drain);
            return;
        }
        current = job;
        const started = Date.now();
        host.capture(job.toplevel, (grab, width, height) => {
            if (grab && job.toplevel && ToplevelManager.toplevels.values.includes(job.toplevel) && !GlobalStates.screenLocked) {
                const next = Object.assign({}, frames);
                next[job.id] = {toplevel: job.toplevel, grab: grab, width: width, height: height, requestedAt: started};
                let recent = order.filter(id => id !== job.id).concat([job.id]);
                while (recent.length > limit) delete next[recent.shift()];
                order = recent;
                frames = next;
            }
            current = null;
            for (const listener of job.callbacks) { if (listener.done) listener.done(); }
            Qt.callLater(drain);
        });
    }
    function prune() {
        const windows = ToplevelManager.toplevels.values;
        const next = Object.assign({}, frames);
        let changed = false;
        for (const id of Object.keys(next)) {
            if (!windows.includes(next[id].toplevel)) { delete next[id]; changed = true; }
        }
        if (changed) { frames = next; order = order.filter(id => !!next[id]); }
    }
    Connections { target: ToplevelManager.toplevels; function onValuesChanged() { root.prune(); } }
    Connections {
        target: GlobalStates
        function onScreenLockedChanged() {
            if (!GlobalStates.screenLocked) return;
            root.frames = ({});
            root.order = [];
            for (const host of root.hosts) host.abort();
        }
    }
}
