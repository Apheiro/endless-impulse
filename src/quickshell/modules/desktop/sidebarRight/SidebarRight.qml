import qs.modules.shared.primitives.common
import qs
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets
import QtQuick
import Quickshell.Io
import Quickshell
import Quickshell.Wayland
import Quickshell.Hyprland

Scope {
    id: root
    property int sidebarWidth: Appearance.sizes.sidebarWidth

    PanelWindow {
        id: panelWindow
        visible: reveal.visible
        contentItem.clip: true
        // Region.item does not track Translate updates reliably. Keep the input
        // rectangle bound to the same animated coordinates as the visible panel.
        mask: Region {
            x: Math.round(sidebarContentLoader.x + (1 - reveal.progress) * root.sidebarWidth)
            y: Math.round(sidebarContentLoader.y)
            width: Math.round(sidebarContentLoader.width)
            height: Math.round(sidebarContentLoader.height)
            radius: Appearance.rounding.screenRounding - Appearance.sizes.hyprlandGapsOut + 1
        }
        SidebarReveal { id: reveal; opened: GlobalStates.sidebarRightOpen }
        readonly property bool wantsFocus: visible && GlobalStates.sidebarRightOpen

        function hide() {
            GlobalStates.sidebarRightOpen = false;
        }

        exclusiveZone: 0
        implicitWidth: sidebarWidth + Appearance.sizes.sidebarOvershootMargin
        WlrLayershell.namespace: "quickshell:sidebarRight"
        WlrLayershell.keyboardFocus: GlobalStates.sidebarRightOpen ? WlrKeyboardFocus.OnDemand : WlrKeyboardFocus.None
        color: "transparent"

        anchors {
            top: true
            right: true
            bottom: true
        }

        onWantsFocusChanged: {
            if (wantsFocus) {
                GlobalFocusGrab.addDismissable(panelWindow);
                QuickPanelState.dismiss();
            } else {
                GlobalFocusGrab.removeDismissable(panelWindow);
            }
        }
        Connections {
            target: GlobalFocusGrab
            function onDismissed() {
                panelWindow.hide();
            }
        }

        Loader {
            id: sidebarContentLoader
            active: reveal.visible || Config?.options.sidebar.keepRightSidebarLoaded
            enabled: GlobalStates.sidebarRightOpen
            transform: Translate { x: (1 - reveal.progress) * root.sidebarWidth }
            anchors {
                fill: parent
                margins: Appearance.sizes.hyprlandGapsOut
                leftMargin: Appearance.sizes.elevationMargin + Appearance.sizes.sidebarOvershootMargin
            }
            width: sidebarWidth - Appearance.sizes.hyprlandGapsOut - Appearance.sizes.elevationMargin
            height: parent.height - Appearance.sizes.hyprlandGapsOut * 2

            focus: GlobalStates.sidebarRightOpen
            Keys.onPressed: event => {
                if (event.key === Qt.Key_Escape) {
                    panelWindow.hide();
                }
            }

            sourceComponent: SidebarRightContent {}
        }
    }

    IpcHandler {
        target: "sidebarRight"

        function toggle(): void {
            GlobalStates.sidebarRightOpen = !GlobalStates.sidebarRightOpen;
        }

        function close(): void {
            GlobalStates.sidebarRightOpen = false;
        }

        function open(): void {
            GlobalStates.sidebarRightOpen = true;
        }
    }

    GlobalShortcut {
        name: "sidebarRightToggle"
        description: "Toggles right sidebar on press"

        onPressed: {
            GlobalStates.sidebarRightOpen = !GlobalStates.sidebarRightOpen;
        }
    }
    GlobalShortcut {
        name: "sidebarRightOpen"
        description: "Opens right sidebar on press"

        onPressed: {
            GlobalStates.sidebarRightOpen = true;
        }
    }
    GlobalShortcut {
        name: "sidebarRightClose"
        description: "Closes right sidebar on press"

        onPressed: {
            GlobalStates.sidebarRightOpen = false;
        }
    }
}
