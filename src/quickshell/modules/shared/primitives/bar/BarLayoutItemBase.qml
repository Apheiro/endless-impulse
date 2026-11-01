import QtQuick
import qs.modules.shared

// Non-content entries (spaces and separators) share the host contract, not a pill.
Item {
    property bool compact: false
    property bool editing: false
    property real spaceSize: 24
    property bool separatorBefore: false
    property bool joinedBefore: false
    property bool joinedAfter: false
    readonly property bool available: true
    readonly property var previewItem: null
    implicitHeight: Appearance.sizes.barHeight
}
