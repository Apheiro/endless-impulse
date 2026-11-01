pragma ComponentBehavior: Bound
import QtQuick
import qs.modules.shared

// Shared visual contract. Feature data and actions belong to the consuming module.
Item {
    id: root
    property bool vertical: false
    property bool compact: false
    property bool editing: false
    property real spaceSize: 24
    property bool separatorBefore: false
    property bool available: true
    property bool interactive: false
    property bool hoverable: true
    property bool active: false
    property bool surfaceEnabled: true
    property real horizontalPadding: Appearance.sizes.barModulePadding
    property real contentWidthLimit: Infinity
    readonly property bool hovered: hover.hovered && hoverable && !editing
    readonly property bool pressed: pointer.pressed
    readonly property color foreground: active ? Appearance.colors.colOnSecondaryContainer
        : !Config.options.bar.borderless && Config.options.bar.showBackground ? Appearance.colors.colOnLayer1 : Appearance.colors.colOnLayer0
    readonly property var previewItem: content.children.length ? content.children[0] : null
    readonly property real naturalContentWidth: {
        let width = 0;
        for (const item of content.children) width = Math.max(width, item.implicitWidth);
        return Math.min(contentWidthLimit, width);
    }
    default property alias contentData: content.data
    property alias contentItem: content
    signal clicked()
    signal secondaryClicked()

    implicitWidth: naturalContentWidth > 0 ? naturalContentWidth + horizontalPadding * 2 : 0
    implicitHeight: Appearance.sizes.barHeight
    visible: available
    opacity: enabled ? 1 : .4

    Rectangle {
        id: surface
        objectName: "bar-module-surface"
        x: root.vertical ? Appearance.sizes.barModuleInset : 0
        y: root.vertical ? 0 : Appearance.sizes.barModuleInset
        width: Math.max(0, root.width - (root.vertical ? Appearance.sizes.barModuleInset * 2 : 0))
        height: Math.max(0, root.height - (root.vertical ? 0 : Appearance.sizes.barModuleInset * 2))
        // Half the actual surface height preserves full pill ends at any bar size.
        radius: Math.min(width, height) / 2
        visible: root.surfaceEnabled
        color: root.active ? Appearance.colors.colSecondaryContainer
            : root.pressed ? Appearance.colors.colLayer1Active
            : root.hovered ? Appearance.colors.colLayer1Hover
            : Config.options.bar.borderless ? "transparent"
            : Config.options.bar.showBackground ? Appearance.colors.colLayer1 : Appearance.colors.colLayer0
        Behavior on color { animation: Appearance.animation.elementMoveFast.colorAnimation.createObject(this) }
    }
    BarSeparator {
        objectName: "bar-module-separator"
        visible: Config.options.bar.borderless && root.separatorBefore
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        height: root.height
    }
    Item {
        id: content
        anchors.fill: parent
        anchors.leftMargin: root.horizontalPadding
        anchors.rightMargin: root.horizontalPadding
        anchors.topMargin: root.vertical ? root.horizontalPadding : 0
        anchors.bottomMargin: root.vertical ? root.horizontalPadding : 0
    }
    HoverHandler { id: hover; enabled: root.hoverable && !root.editing }
    MouseArea {
        id: pointer
        anchors.fill: parent
        enabled: root.interactive && !root.editing
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        cursorShape: Qt.PointingHandCursor
        onClicked: event => event.button === Qt.LeftButton ? root.clicked() : root.secondaryClicked()
    }
}
