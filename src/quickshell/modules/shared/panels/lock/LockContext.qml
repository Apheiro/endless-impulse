import qs
import qs.modules.shared
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Services.Pam

Scope {
    id: root

    enum ActionEnum { Unlock, Poweroff, Reboot }

    signal shouldReFocus()
    signal unlocked(targetAction: var)
    signal failed()

    // These properties are in the context and not individual lock surfaces
    // so all surfaces can share the same state.
    property string currentText: ""
    property bool unlockInProgress: false
    property bool showFailure: false
    property bool fingerprintsConfigured: false
    property var targetAction: LockContext.ActionEnum.Unlock
    property bool alsoInhibitIdle: false
    readonly property string hostPamPython: Quickshell.env("DOTS_HOST_PAM_PYTHON")

    function completePasswordUnlock(success) {
        if (success) {
            root.unlocked(root.targetAction);
            stopFingerPam();
        } else {
            root.clearText();
            root.unlockInProgress = false;
            GlobalStates.screenUnlockFailed = true;
            root.showFailure = true;
        }
    }

    function resetTargetAction() {
        root.targetAction = LockContext.ActionEnum.Unlock;
    }

    function clearText() {
        root.currentText = "";
    }

    function resetClearTimer() {
        passwordClearTimer.restart();
    }

    function reset() {
        root.resetTargetAction();
        root.clearText();
        root.unlockInProgress = false;
        if (hostPam.running) hostPam.running = false;
        stopFingerPam();
    }

    Timer {
        id: passwordClearTimer
        interval: 10000
        onTriggered: {
            root.reset();
        }
    }

    onCurrentTextChanged: {
        if (currentText.length > 0) {
            showFailure = false;
            GlobalStates.screenUnlockFailed = false;
        }
        GlobalStates.screenLockContainsCharacters = currentText.length > 0;
        passwordClearTimer.restart();
    }

    function tryUnlock(alsoInhibitIdle = false) {
        if (root.unlockInProgress) return;
        root.alsoInhibitIdle = alsoInhibitIdle;
        root.unlockInProgress = true;
        passwordClearTimer.stop();
        if (root.hostPamPython) {
            hostPam.payload = JSON.stringify(root.currentText) + "\n";
            hostPam.stdinEnabled = true;
            hostPam.running = true;
        } else {
            pam.start();
        }
    }

    function tryFingerUnlock() {
        if (root.fingerprintsConfigured) {
            fingerPam.start();
        }
    }

    function stopFingerPam() {
        if (fingerPam.active) {
            fingerPam.abort();
        }
    }

    Process {
        id: fingerprintCheckProc
        running: true
        command: ["bash", "-c", "fprintd-list $(whoami)"]
        stdout: StdioCollector {
            id: fingerprintOutputCollector
            onStreamFinished: {
                root.fingerprintsConfigured = fingerprintOutputCollector.text.includes("Fingerprints for user");
            }
        }
        onExited: (exitCode, exitStatus) => {
            if (exitCode !== 0) {
                // console.warn("[LockContext] fprintd-list command exited with error:", exitCode, exitStatus);
                root.fingerprintsConfigured = false;
            }
        }
    }
    
    Process {
        id: hostPam
        property string payload: ""
        command: [root.hostPamPython, "-I", Quickshell.shellPath("scripts/lock/authenticate.py")]
        environment: ({ "LD_LIBRARY_PATH": "", "LD_PRELOAD": "", "PYTHONHOME": "", "PYTHONPATH": "" })
        onStarted: {
            write(payload);
            payload = "";
            stdinEnabled = false;
        }
        onExited: (exitCode, exitStatus) => {
            payload = "";
            if (!root.unlockInProgress) return;
            if (exitCode !== 0 && exitCode !== 1)
                console.warn("[LockContext] Host PAM could not complete authentication");
            root.completePasswordUnlock(exitCode === 0 && exitStatus === 0);
        }
    }

    PamContext {
        id: pam

        // pam_unix will ask for a response for the password prompt
        onPamMessage: {
            if (this.responseRequired) {
                this.respond(root.currentText);
            }
        }

        // pam_unix won't send any important messages so all we need is the completion status.
        onCompleted: result => {
            root.completePasswordUnlock(result == PamResult.Success);
        }
    }

    PamContext {
        id: fingerPam

        configDirectory: "pam"
        config: "fprintd.conf"

        onCompleted: result => {
            if (result == PamResult.Success) {
                root.unlocked(root.targetAction);
                stopFingerPam();
            } else if (result == PamResult.Error) { // if timeout or etc..
                tryFingerUnlock()
            }
        }
    }
}
