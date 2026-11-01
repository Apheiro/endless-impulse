pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import Quickshell
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets

Flickable {
    required property var editor
    id: section
    required property var entries
    property bool alignEnd: false
    property var previousEntry: null
    property alias row: row
    readonly property bool flexible: entries.some(item => item.type === "flex")
    height: editor.barHeight
    contentWidth: Math.max(width, row.width)
    contentHeight: height
    interactive: !editor.dragging && contentWidth > width
    clip: contentWidth > width
    flickableDirection: Flickable.HorizontalFlick
    boundsBehavior: Flickable.StopAtBounds
    onContentWidthChanged: contentX = alignEnd ? Math.max(0, contentWidth - width) : Math.min(contentX, Math.max(0, contentWidth - width))
    onWidthChanged: contentX = alignEnd ? Math.max(0, contentWidth - width) : Math.min(contentX, Math.max(0, contentWidth - width))
    ScrollBar.horizontal: StyledScrollBar {
        visible: editor.editing && section.contentWidth > section.width
        policy: ScrollBar.AlwaysOn
        orientation: Qt.Horizontal
        topPadding: 0; bottomPadding: 0
        height: 4; z: 3
        contentItem: Rectangle { implicitHeight: 4; radius: 2; color: Appearance.colors.colOutlineVariant }
    }
    RowLayout {
        id: row
        height: section.height
        width: section.flexible ? Math.max(section.width, implicitWidth) : implicitWidth
        x: section.alignEnd ? Math.max(0, section.width - width) : 0
        spacing: editor.itemSpacing
        Repeater {
            model: ScriptModel { values: section.entries; objectProp: "key" }
            delegate: BarLayoutTile {
                editor: section.editor
                required property var modelData
                required property int index
                entry: modelData
                scrollTarget: section
                separatorBefore: section.editor.dividerBetween(index > 0 ? section.entries[index - 1] : section.previousEntry, modelData)
            }
        }
    }
}
