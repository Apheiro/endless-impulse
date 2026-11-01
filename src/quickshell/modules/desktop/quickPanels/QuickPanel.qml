pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Wayland
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets

Scope {
    id: root
    Component { id: audioContent; QuickAudioContent {} }
    Component { id: networkContent; QuickNetworkContent {} }
    Component { id: bluetoothContent; QuickBluetoothContent {} }
    function componentFor(section) { return section === "audio" ? audioContent : section === "network" ? networkContent : bluetoothContent; }
    Loader {
        id: windowLoader
        active: QuickPanelState.section !== ""
        sourceComponent: PanelWindow {
            id: panel
            property string displayedSection: ""
            property string phase: "initial"
            property bool initialContent: true
            property real panelHeight: 180
            readonly property string requestedSection: QuickPanelState.section
            readonly property real desiredHeight: Math.max(1, Math.min(screen.height * 0.78, body.implicitHeight + Appearance.sizes.elevationMargin * 2 + 32))
            readonly property bool transitioning: phase !== "idle"
            screen: Quickshell.screens.find(s => s.name === QuickPanelState.controller?.screenName) ?? Quickshell.screens[0]
            anchors { top: true; right: true }
            // Match SidebarRight: normal exclusion plus the configured outer gap.
            // Subtract the reserved shadow margin to align the visible surface.
            margins.top: Appearance.sizes.hyprlandGapsOut - Appearance.sizes.elevationMargin
            margins.right: 8
            implicitWidth: Math.min(420, screen.width - 16)
            implicitHeight: Math.round(panelHeight)
            exclusiveZone: 0
            exclusionMode: ExclusionMode.Normal
            color: "transparent"
            WlrLayershell.namespace: "quickshell:quick-panel"
            WlrLayershell.layer: WlrLayer.Overlay
            WlrLayershell.keyboardFocus: WlrKeyboardFocus.OnDemand
            mask: Region { item: surface }

            function installLatest() {
                if (!requestedSection) return;
                resizeAnimation.stop();
                phase = "resize";
                displayedSection = requestedSection;
                content.sourceComponent = root.componentFor(displayedSection);
                Qt.callLater(resizeToContent);
            }
            function resizeToContent() {
                if (!requestedSection || (phase !== "resize" && phase !== "idle")) return;
                if (initialContent) {
                    initialContent = false;
                    panelHeight = desiredHeight;
                    showContent();
                } else if (Math.abs(panelHeight - desiredHeight) < 1) {
                    resizeAnimation.stop();
                    if (phase === "resize") showContent();
                } else {
                    resizeAnimation.stop();
                    resizeAnimation.to = desiredHeight;
                    resizeAnimation.start();
                }
            }
            function showContent() {
                if (requestedSection !== displayedSection) { installLatest(); return; }
                phase = "in";
                fadeIn.start();
            }
            function navigate() {
                if (!requestedSection || phase === "initial") return;
                if (phase === "out") return; // Its completion reads the latest request.
                if (requestedSection === displayedSection) return;
                surface.forceActiveFocus();
                if (phase === "resize") { installLatest(); return; }
                fadeIn.stop();
                resizeAnimation.stop();
                phase = "out";
                fadeOut.start();
            }
            onRequestedSectionChanged: navigate()
            onDesiredHeightChanged: if (phase === "idle" || phase === "resize") Qt.callLater(resizeToContent)
            Component.onCompleted: {
                GlobalFocusGrab.addDismissable(panel);
                installLatest();
            }
            Component.onDestruction: GlobalFocusGrab.removeDismissable(panel)
            Connections { target: GlobalFocusGrab; function onDismissed() { QuickPanelState.dismiss(); } }
            NumberAnimation {
                id: fadeOut
                target: body
                property: "opacity"
                to: 0
                duration: Appearance.animation.elementMoveFast.duration
                easing.type: Appearance.animation.elementMoveFast.type
                easing.bezierCurve: Appearance.animation.elementMoveFast.bezierCurve
                onFinished: panel.installLatest()
            }
            NumberAnimation {
                id: resizeAnimation
                target: panel
                property: "panelHeight"
                duration: Appearance.animation.elementResize.duration
                easing.type: Appearance.animation.elementResize.type
                easing.bezierCurve: Appearance.animation.elementResize.bezierCurve
                onFinished: if (panel.phase === "resize") panel.showContent()
            }
            NumberAnimation {
                id: fadeIn
                target: body
                property: "opacity"
                to: 1
                duration: Appearance.animation.elementMoveFast.duration
                easing.type: Appearance.animation.elementMoveFast.type
                easing.bezierCurve: Appearance.animation.elementMoveFast.bezierCurve
                onFinished: {
                    panel.phase = "idle";
                    panel.resizeToContent();
                }
            }
            StyledRectangularShadow { target: surface }
            Rectangle {
                id: surface
                anchors.fill: parent
                anchors.margins: Appearance.sizes.elevationMargin
                radius: Appearance.rounding.large
                color: Appearance.colors.colLayer0
                border.width: 1
                border.color: Appearance.colors.colLayer0Border
                focus: true
                Keys.onEscapePressed: QuickPanelState.dismiss()
                Component.onCompleted: forceActiveFocus()
                ColumnLayout {
                    id: body
                    objectName: "quick-panel-body"
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 12
                    opacity: 0
                    enabled: panel.phase === "idle"
                    clip: true
                    RowLayout {
                        Layout.fillWidth: true
                        MaterialSymbol { text: ({audio: "volume_up", network: "lan", bluetooth: "bluetooth"})[panel.displayedSection] || ""; iconSize: 22; color: Appearance.colors.colPrimary }
                        StyledText { Layout.fillWidth: true; text: ({audio: Translation.tr("Sound"), network: Translation.tr("Network"), bluetooth: Translation.tr("Bluetooth")})[panel.displayedSection] || ""; font.weight: Font.DemiBold }
                        RippleButtonWithIcon { materialIcon: "close"; mainText: ""; onClicked: QuickPanelState.dismiss() }
                    }
                    Loader {
                        id: content
                        objectName: "quick-panel-content"
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                    }

                }
            }
        }
    }
}
