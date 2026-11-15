pragma Singleton
pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root
    // Only the presentation host enables publishing; Settings is a subscriber.
    property bool host: false
    property bool owner: false
    property bool localActive: false
    property bool remoteActive: false
    property bool presentationReady: false
    property bool subscriptionReady: false
    // Unknown subscription state is not an authentication conversation. Keep it
    // separate so explicit dismissal is never vetoed merely by process startup.
    readonly property bool active: localActive || remoteActive
    readonly property bool grabReady: host || subscriptionReady

    onLocalActiveChanged: {
        presentationReady = false;
        publish();
    }
    function startHost() {
        if (publisher.running) return;
        host = false;
        Qt.callLater(() => { root.host = true; });
    }
    function stopHost() { host = false; }
    function publish() {
        if (owner && publisher.running) publisher.write(localActive ? "1\n" : "0\n");
    }
    Process {
        id: publisher
        running: root.host
        command: ["python3", Quickshell.shellPath("scripts/polkit/focus.py"), "publish"]
        stdinEnabled: true
        stdout: SplitParser {
            onRead: data => {
                const value = JSON.parse(data);
                if (value.event === "owner") {
                    root.owner = true;
                    root.publish();
                } else if (value.event === "present") {
                    root.presentationReady = root.localActive;
                    if (!value.synchronized) console.warn("Authentication: a focus subscriber did not acknowledge before the presentation deadline");
                } else if (value.event === "expired") {
                    console.warn("Authentication: focus lease expired; releasing remote focus guards");
                }
            }
        }
        onExited: {
            root.owner = false;
            root.presentationReady = false;
            console.warn("Authentication: native host unavailable or already owned by another shell. See docs/features/polkit.md for recovery.");
        }
    }
    Timer {
        interval: 5000
        repeat: true
        running: root.owner && root.localActive
        onTriggered: root.publish()
    }
    Timer {
        interval: 2000
        running: !root.subscriptionReady
        onTriggered: {
            root.subscriptionReady = true;
            console.warn("Authentication: initial subscription timed out; focus protection unavailable until synchronized");
        }
    }
    Process {
        id: subscriber
        running: true
        command: ["python3", Quickshell.shellPath("scripts/polkit/focus.py"), "subscribe"]
        stdinEnabled: true
        stdout: SplitParser {
            onRead: data => {
                const value = JSON.parse(data);
                root.remoteActive = value.active;
                root.subscriptionReady = true;
                // Bindings must release grabs before acknowledging presentation.
                Qt.callLater(() => { if (subscriber.running && value.revision >= 0) subscriber.write(value.revision + "\n"); });
            }
        }
        onExited: {
            root.remoteActive = false;
            root.subscriptionReady = true;
            console.warn("Authentication: focus subscription stopped; remote protection unavailable");
        }
    }
}
