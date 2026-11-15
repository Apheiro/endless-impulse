pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import Quickshell.Hyprland
import qs.services
import qs.modules.shared
import qs.modules.shared.primitives.common

Scope {
    id: root
    readonly property var presentation: hostLoader.item
    Component.onCompleted: AuthenticationFocusState.host = true
    Component.onDestruction: {
        AuthenticationFocusState.localActive = false;
        AuthenticationFocusState.host = false;
    }
    IpcHandler {
        target: "authentication"
        function status(): string {
            return AuthenticationFocusState.owner
                ? (PolkitService.registered ? "registered" : "registration-failed-or-pending")
                : "disabled-or-session-already-owned";
        }
        function stop(): void { AuthenticationFocusState.stopHost(); }
        function start(): void { AuthenticationFocusState.startHost(); }
    }
    // Exclusive session ownership precedes construction/registration of PolkitAgent.
    Loader {
        id: hostLoader
        active: AuthenticationFocusState.owner
        sourceComponent: Scope {
            id: host
            objectName: "polkit-presentation"
            Component.onDestruction: AuthenticationFocusState.localActive = false
            readonly property bool authenticating: PolkitService.conversationActive
            readonly property alias panelWindow: panel
            readonly property alias card: surface
            property bool mapped: false
            property real progress: 0
            property var selectedScreen: null
            function present() {
                if (!authenticating || !AuthenticationFocusState.presentationReady) return;
                if (!mapped) selectScreen();
                mapped = true;
                motion.to = 1;
                motion.restart();
            }
            function selectScreen(screens = Quickshell.screens, focusedName = Hyprland.focusedMonitor?.name) {
                selectedScreen = screens.find(s => s.name === focusedName) ?? screens[0] ?? null;
            }
            onAuthenticatingChanged: {
                if (authenticating) {
                    AuthenticationFocusState.localActive = true;
                    present();
                } else {
                    motion.to = 0;
                    motion.restart();
                }
            }
            Component.onCompleted: {
                if (authenticating) {
                    AuthenticationFocusState.localActive = true;
                    present();
                }
            }
            Connections {
                target: AuthenticationFocusState
                function onPresentationReadyChanged() { host.present(); }
            }
            Connections {
                target: Quickshell
                function onScreensChanged() {
                    if (host.mapped && Quickshell.screens.indexOf(host.selectedScreen) < 0) host.selectScreen();
                }
            }
            NumberAnimation {
                id: motion
                target: host
                property: "progress"
                duration: Config.options.appearance.reducedMotion ? 0 : Appearance.animation.elementMoveFast.duration
                easing.type: Easing.InOutCubic
                onFinished: {
                    if (to === 0 && !host.authenticating) {
                        host.mapped = false;
                        // The surface has unmapped before guards are restored.
                        Qt.callLater(() => {
                            if (!host.authenticating && !host.mapped) AuthenticationFocusState.localActive = false;
                        });
                    }
                }
            }
            PanelWindow {
                id: panel
                objectName: "polkit-panel"
                visible: host.mapped
                screen: host.selectedScreen
                anchors.bottom: true
                exclusionMode: ExclusionMode.Ignore
                exclusiveZone: 0
                color: "transparent"
                WlrLayershell.namespace: "quickshell:polkit"
                WlrLayershell.layer: WlrLayer.Overlay
                WlrLayershell.keyboardFocus: visible && host.authenticating ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None
                readonly property real shadowMargin: Appearance.sizes.elevationMargin
                implicitWidth: Math.min(480 + 2 * shadowMargin, screen?.width ?? 480)
                implicitHeight: Math.min(content.implicitHeight + 2 * shadowMargin, screen?.height ?? 600)
                mask: Region { item: surface }
                Item {
                    anchors.fill: parent
                    clip: true
                    StyledRectangularShadow { target: surface }
                    PanelSurface {
                        id: surface
                        objectName: "polkit-surface"
                        x: panel.shadowMargin
                        y: panel.shadowMargin + (1 - host.progress) * panel.height
                        width: panel.width - 2 * panel.shadowMargin
                        height: panel.height - 2 * panel.shadowMargin
                        PolkitPrompt {
                            id: content
                            anchors.fill: parent
                        }
                    }
                }
            }
        }
    }
}
