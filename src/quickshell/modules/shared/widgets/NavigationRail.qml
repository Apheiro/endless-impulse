import QtQuick
import QtQuick.Layouts
import qs.modules.shared
import qs.modules.shared.widgets

ColumnLayout { // Window content with navigation rail and content pane
    id: root
    property bool expanded: true
    property int currentIndex: 0
    spacing: 5
}
