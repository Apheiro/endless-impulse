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
    readonly property var moduleItem: loader.item
    readonly property var previewItem: loader.item?.previewItem ?? loader.item
    readonly property bool present: editing || (loader.item?.visible ?? false)
    readonly property bool fallback: editing && !(loader.item?.visible && loader.item.implicitWidth > 0)
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
