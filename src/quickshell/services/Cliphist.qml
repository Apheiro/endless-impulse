pragma Singleton
pragma ComponentBehavior: Bound

import qs.modules.shared
import qs.modules.shared.functions
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root
    property real pasteDelay: 0.05
    property bool sloppySearch: Config.options?.search.sloppy ?? false
    property real scoreThreshold: 0.2
    property list<string> entries: []
    property list<string> historyEntries: []
    readonly property string latestEntry: historyEntries[0] ?? ""
    property list<string> pinned: []
    property int removableCount: 0
    property string error: ""
    property var queue: []
    property bool inFlight: false
    property bool refreshPending: false
    readonly property bool busy: inFlight || queue.length > 0
    readonly property string helper: Quickshell.shellPath("scripts/clipboard/history.py")
    readonly property var preparedEntries: entries.map(a => ({
        name: Fuzzy.prepare(`${a.replace(/^\s*\S+\s+/, "")}`),
        entry: a
    }))
    function fuzzyQuery(search: string): var {
        if (search.trim() === "") {
            return entries;
        }
        if (root.sloppySearch) {
            const results = entries.slice(0, 100).map(str => ({
                entry: str,
                score: Levendist.computeTextMatchScore(str.toLowerCase(), search.toLowerCase())
            })).filter(item => item.score > root.scoreThreshold)
                .sort((a, b) => b.score - a.score)
            return results
                .map(item => item.entry)
        }

        return Fuzzy.go(search, preparedEntries, {
            all: true,
            key: "name"
        }).map(r => {
            return r.obj.entry
        });
    }

    function entryIsImage(entry) {
        return /^\[\[.*binary data.*\d+x\d+.*\]\]$/.test(StringUtils.cleanCliphistEntry(entry));
    }

    function entryId(entry) { return entry.split("\t")[0]; }
    function isPinned(entry) { return pinned.includes(entryId(entry)); }
    function cacheCommand(entry, path) { return ["python3", helper, "cache", entryId(entry), path]; }
    function refresh() {
        if (busy) { refreshPending = true; return; }
        request("list");
    }
    function request(action, payload = {}) {
        queue = [...queue, {action, payload}];
        drain();
    }
    function drain() {
        if (inFlight || !queue.length) return;
        const next = queue[0];
        queue = queue.slice(1);
        inFlight = true;
        worker.payload = JSON.stringify(next.payload);
        worker.received = false;
        worker.stdinEnabled = next.action !== "list";
        worker.command = ["python3", helper, next.action];
        error = "";
        worker.running = true;
    }
    function copy(entry) { Quickshell.execDetached(["python3", helper, "copy", entryId(entry)]); }
    function paste(entry) { Quickshell.execDetached(["python3", helper, "paste", entryId(entry)]); }
    function togglePin(entry) { request(isPinned(entry) ? "unpin" : "pin", {entry: entryId(entry)}); }
    function deleteEntry(entry) { request("delete", {entry: entryId(entry)}); }
    function clearUnpinned() { request("clear"); }
    function superpaste(count, isImage = false) {
        request("superpaste", {entries: historyEntries.filter(entry => !isImage || entryIsImage(entry))
            .slice(0, count).map(entryId), delay: pasteDelay});
    }

    Connections {
        target: Quickshell
        function onClipboardTextChanged() {
            delayedUpdateTimer.restart()
        }
    }

    Timer {
        id: delayedUpdateTimer
        interval: Config.options.hacks.arbitraryRaceConditionDelay
        repeat: false
        onTriggered: {
            root.refresh()
        }
    }

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
                    if (!result.ok) { root.error = result.error; return; }
                    root.entries = result.entries;
                    root.historyEntries = result.historyEntries;
                    root.pinned = result.pinned;
                    root.removableCount = result.removableCount;
                } catch (error) { root.error = "Could not read clipboard history."; }
            }
        }
        onExited: {
            root.inFlight = false;
            if (!received) root.error = "Could not start the clipboard helper.";
            if (root.refreshPending) {
                root.refreshPending = false;
                root.queue = [...root.queue, {action: "list", payload: {}}];
            }
            Qt.callLater(root.drain);
        }
    }

    IpcHandler {
        target: "cliphistService"

        function update(): void {
            root.refresh()
        }
    }
}
