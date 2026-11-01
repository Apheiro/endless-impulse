pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import qs.services
import qs.modules.shared
import qs.modules.shared.primitives.common

// Dynamic host only: modules own content, primitives own presentation.
Item {
    id: root
    required property string widgetType
    property bool compact: false
    property bool editing: false
    property real spaceSize: 24
    property bool separatorBefore: false
    property bool joinedBefore: false
    property bool joinedAfter: false
    readonly property var moduleItem: loader.item
    readonly property var previewItem: loader.item?.previewItem ?? loader.item
    // Item.visible includes ancestor visibility. The tile binds its own visibility
    // to present, so reading the child's visible here would latch a loading tile
    // hidden forever. Availability is module state, independent of its parents.
    readonly property bool moduleAvailable: loader.item !== null && (loader.item.available ?? true)
    readonly property bool present: editing || moduleAvailable
    readonly property bool fallback: editing && !(moduleAvailable && loader.item.implicitWidth > 0)
    implicitWidth: fallback ? 140 : present ? (loader.item?.implicitWidth ?? 0) : 0
    implicitHeight: Appearance.sizes.barHeight
    Loader {
        id: loader
        anchors.fill: parent
        source: BarModuleRegistry.sourceFor(root.widgetType)
        onLoaded: {
            item.compact = Qt.binding(() => root.compact);
            item.editing = Qt.binding(() => root.editing);
            item.spaceSize = Qt.binding(() => root.spaceSize);
            item.separatorBefore = Qt.binding(() => root.separatorBefore);
            item.joinedBefore = Qt.binding(() => root.joinedBefore);
            item.joinedAfter = Qt.binding(() => root.joinedAfter);
        }
    }
    RowLayout {
        anchors.centerIn: parent
        width: Math.min(parent.width - 8, implicitWidth)
        visible: root.fallback
        MaterialSymbol { text: BarLayout.info(root.widgetType).icon; iconSize: 22; color: Appearance.colors.colOnLayer0 }
        StyledText { Layout.fillWidth: true; visible: root.width > 85; text: BarLayout.info(root.widgetType).name; elide: Text.ElideRight; font.pixelSize: Appearance.font.pixelSize.smaller }
    }
}
