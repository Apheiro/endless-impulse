pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Hyprland
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets

RippleButton {
    id: root
    property color foreground: Appearance.colors.colOnLayer2
    implicitHeight: 26
    implicitWidth: ScreenRecorder.active ? recordingContent.implicitWidth + (surfaceVisible ? Appearance.sizes.barModulePadding * 2 : 0) : implicitHeight
    padding: 0
    buttonRadius: height / 2
    colBackground: ScreenRecorder.active ? Appearance.colors.colLayer2 : "transparent"
    colBackgroundHover: Appearance.colors.colLayer2Hover
    enabled: !ScreenRecorder.busy || ScreenRecorder.active
    onClicked: ScreenRecorder.active ? ScreenRecorder.stop() : ScreenRecorder.start(undefined, root.QsWindow.window?.screen?.name)
    function toggleMenu() {
        if (menu.visible) { menu.visible = false; return; }
        menu.anchor.updateAnchor();
        menu.visible = true;
        Qt.callLater(() => menu.anchor.updateAnchor());
    }
    altAction: () => root.toggleMenu()
    onWidthChanged: { if (menu.visible) menu.anchor.updateAnchor(); }
    contentItem: Item {
        implicitWidth: ScreenRecorder.active ? recordingContent.implicitWidth : 26
        implicitHeight: 26
        MaterialSymbol {
            anchors.centerIn: parent
            visible: !ScreenRecorder.active
            text: "videocam"
            fill: 1
            iconSize: Appearance.font.pixelSize.large
            color: root.foreground
        }
        RecordingIndicator {
            id: recordingContent
            foreground: root.foreground
            anchors.centerIn: parent
        }
    }
    property var tooltip: StyledToolTip {
        parent: root
        text: ScreenRecorder.failed ? ScreenRecorder.message : ScreenRecorder.active ? Translation.tr("Stop recording") + " · " + ScreenRecorder.elapsedText : Translation.tr("Record · Right-click for capture options")
    }
    property var contextMenu: PopupWindow {
        id: menu
        visible: false
        color: "transparent"
        anchor {
            item: root
            adjustment: PopupAdjustment.SlideX | PopupAdjustment.SlideY
            gravity: Config.options.bar.bottom ? Edges.Top : Edges.Bottom
            edges: Config.options.bar.bottom ? Edges.Top : Edges.Bottom
        }
        readonly property real shadowMargin: Appearance.sizes.elevationMargin
        implicitWidth: 270 + shadowMargin * 2
        implicitHeight: entries.implicitHeight + 20 + shadowMargin * 2
        mask: Region { item: popupBackground }
        StyledRectangularShadow { target: popupBackground }
        PanelSurface {
            id: popupBackground
            objectName: "recording-menu-surface"
            anchors.fill: parent
            anchors.margins: menu.shadowMargin
            radius: Appearance.rounding.windowRounding
        }
        ColumnLayout {
            id: entries
            anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10 + menu.shadowMargin }
            spacing: 4
            StyledText { text: "GPU Screen Recorder"; font.pixelSize: Appearance.font.pixelSize.small; Layout.margins: 6 }
            RippleButtonWithIcon {
                Layout.fillWidth: true
                materialIcon: "screenshot_region"; mainText: Translation.tr("Record a region")
                enabled: !ScreenRecorder.active && !ScreenRecorder.busy
                onClicked: { menu.visible = false; ScreenRecorder.start("region"); }
            }
            RippleButtonWithIcon {
                Layout.fillWidth: true
                materialIcon: "fullscreen"; mainText: Translation.tr("Record full screen")
                enabled: !ScreenRecorder.active && !ScreenRecorder.busy
                onClicked: { menu.visible = false; ScreenRecorder.start("fullscreen", root.QsWindow.window?.screen?.name); }
            }
            RippleButtonWithIcon {
                Layout.fillWidth: true
                visible: ScreenRecorder.active && ["record", "audio"].includes(ScreenRecorder.state.mode)
                materialIcon: ScreenRecorder.paused ? "play_arrow" : "pause"
                mainText: ScreenRecorder.paused ? Translation.tr("Resume") : Translation.tr("Pause")
                enabled: ScreenRecorder.recording && !ScreenRecorder.busy
                onClicked: { menu.visible = false; ScreenRecorder.pause(); }
            }
            RippleButtonWithIcon {
                Layout.fillWidth: true
                visible: ScreenRecorder.active && ScreenRecorder.state.mode === "replay"
                materialIcon: "save"; mainText: Translation.tr("Save replay")
                enabled: !ScreenRecorder.busy
                onClicked: { menu.visible = false; ScreenRecorder.saveReplay(); }
            }
            RippleButtonWithIcon {
                Layout.fillWidth: true
                visible: ScreenRecorder.active && ["replay", "stream"].includes(ScreenRecorder.state.mode) && !!ScreenRecorder.settings.parallelDirectory
                materialIcon: "video_library"; mainText: Translation.tr("Start / save parallel recording")
                enabled: !ScreenRecorder.busy
                onClicked: { menu.visible = false; ScreenRecorder.parallel(); }
            }
            RippleButtonWithIcon {
                Layout.fillWidth: true
                visible: ScreenRecorder.active
                materialIcon: "stop"; mainText: Translation.tr("Stop session")
                enabled: !ScreenRecorder.busy
                onClicked: { menu.visible = false; ScreenRecorder.stop(); }
            }
        }
        HyprlandFocusGrab { active: menu.visible; windows: [root.QsWindow.window, menu]; onCleared: menu.visible = false }
    }
}
