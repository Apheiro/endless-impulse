pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import Quickshell
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets

Item {
    required property var editor
    id: tile
    required property var entry
    property var scrollTarget: null
    property alias presenter: presenter
    readonly property string instanceKey: entry.key
    readonly property bool locked: entry.locked ?? false
    readonly property bool placeholder: entry.placeholder ?? false
    readonly property bool dragSource: editor.dragging && editor.drag?.key === instanceKey
    readonly property bool collapsed: dragSource && editor.layout.centerKey !== instanceKey
    readonly property bool flexible: entry.type === "flex" && !collapsed
    readonly property bool joinedBefore: editor.adjacentModule(tile, -1) !== null
    readonly property bool joinedAfter: editor.adjacentModule(tile, 1) !== null
    implicitWidth: collapsed ? 0 : placeholder ? editor.dragWidth : presenter.implicitWidth
    implicitHeight: editor.barHeight
    Layout.fillWidth: flexible
    Layout.minimumWidth: implicitWidth
    Layout.maximumWidth: flexible ? Infinity : implicitWidth
    Layout.preferredWidth: implicitWidth
    Layout.rightMargin: collapsed ? -editor.itemSpacing : 0
    visible: placeholder || presenter.present
    Behavior on x {
        enabled: tile.editor.dragging
        animation: Appearance.animation.elementMoveFast.numberAnimation.createObject(this)
    }
    BarWidget {
        id: presenter
        objectName: "bar-presenter-" + tile.instanceKey
        width: tile.collapsed ? tile.editor.dragWidth : tile.width
        height: tile.height
        visible: !tile.placeholder
        widgetType: tile.placeholder ? "" : tile.entry.type
        spaceSize: tile.entry.size ?? 24
        separatorBefore: tile.joinedBefore
        joinedBefore: tile.joinedBefore
        joinedAfter: tile.joinedAfter
        compact: editor.compact
        editing: !tile.placeholder && editor.editing
    }
    Rectangle {
        objectName: "bar-panel-selection"
        anchors.fill: parent; anchors.margins: 1
        visible: editor.editing && !tile.placeholder && !tile.dragSource && BarLayout.selectedKey === tile.instanceKey
        color: "transparent"; radius: Appearance.rounding.small
        border.width: 1; border.color: Appearance.colors.colPrimary
    }
    BarEditHandle {
        anchors.fill: parent
        visible: editor.editing && !tile.locked && !tile.placeholder
        editor: tile.editor
        widgetType: tile.entry.type
        widgetKey: tile.instanceKey
        scrollTarget: tile.scrollTarget
    }
    Rectangle {
        objectName: "bar-drop-placeholder"
        anchors.fill: parent
        anchors.topMargin: Appearance.sizes.barModuleInset + tile.editor.outerMargin
        anchors.bottomMargin: Appearance.sizes.barModuleInset + tile.editor.outerMargin
        visible: tile.placeholder || tile.dragSource && !tile.collapsed
        radius: Appearance.rounding.unsharpen
        color: Appearance.colors.colLayer1Hover
    }
}
