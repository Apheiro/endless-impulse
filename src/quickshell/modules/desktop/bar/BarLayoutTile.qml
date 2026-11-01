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
    property bool separatorBefore: false
    readonly property string instanceKey: entry.key
    readonly property bool locked: entry.locked ?? false
    readonly property bool flexible: entry.type === "flex"
    implicitWidth: presenter.implicitWidth
    implicitHeight: editor.barHeight
    Layout.fillWidth: flexible
    Layout.minimumWidth: implicitWidth
    Layout.maximumWidth: flexible ? Infinity : implicitWidth
    Layout.preferredWidth: implicitWidth
    visible: presenter.present
    opacity: editor.dragging && editor.drag?.key === instanceKey ? 0.4 : 1
    BarWidget {
        id: presenter
        objectName: "bar-presenter-" + tile.instanceKey
        anchors.fill: parent
        widgetType: tile.entry.type
        spaceSize: tile.entry.size ?? 24
        separatorBefore: tile.separatorBefore
        compact: editor.compact
        editing: editor.editing
    }
    Rectangle {
        objectName: "bar-panel-selection"
        anchors.fill: parent; anchors.margins: 1
        visible: editor.editing && (BarLayout.selectedKey === tile.instanceKey || editor.drag?.key === tile.instanceKey)
        color: "transparent"; radius: Appearance.rounding.small
        border.width: 1; border.color: Appearance.colors.colPrimary
    }
    BarEditHandle {
        anchors.fill: parent
        visible: editor.editing && !tile.locked
        editor: tile.editor
        widgetType: tile.entry.type
        widgetKey: tile.instanceKey
        scrollTarget: tile.scrollTarget
    }
}
