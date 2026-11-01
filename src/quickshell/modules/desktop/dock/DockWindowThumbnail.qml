pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import qs
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets

Item {
    id: root
    required property var toplevel
    property bool sampling: false
    property bool minimized: false
    readonly property bool hasImage: String(DockThumbnailCache.image(toplevel)) !== ""
    implicitWidth: DockThumbnailCache.size(toplevel).width
    implicitHeight: DockThumbnailCache.size(toplevel).height

    function refresh() {
        tick.stop();
        if (!sampling || minimized || GlobalStates.screenLocked) return;
        DockThumbnailCache.capture(toplevel, () => {
            if (root && root.sampling && !root.minimized && !GlobalStates.screenLocked) tick.restart();
        }, () => !!root && root.sampling && !root.minimized && !GlobalStates.screenLocked);
    }
    onSamplingChanged: { if (sampling) DockThumbnailCache.touch(toplevel); refresh(); }
    onMinimizedChanged: refresh()
    onToplevelChanged: refresh()
    Component.onCompleted: refresh()
    Timer { id: tick; interval: 1000; onTriggered: root.refresh() }
    Image {
        anchors.fill: parent
        visible: root.hasImage
        source: DockThumbnailCache.image(root.toplevel)
        fillMode: Image.PreserveAspectFit
        cache: false
    }
    ColumnLayout {
        anchors.centerIn: parent
        visible: !root.hasImage
        MaterialSymbol { Layout.alignment: Qt.AlignHCenter; text: root.minimized ? "minimize" : "window"; iconSize: 32 }
        StyledText { text: root.minimized ? Translation.tr("Minimized") : Translation.tr("Preview"); color: Appearance.colors.colSubtext }
    }
}
