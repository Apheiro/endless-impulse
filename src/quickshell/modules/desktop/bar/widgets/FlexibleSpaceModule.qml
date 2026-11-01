pragma ComponentBehavior: Bound
import QtQuick
import qs
import qs.services
import qs.modules.shared
import qs.modules.shared.primitives.common
import qs.modules.shared.primitives.bar
import qs.modules.desktop.bar

BarLayoutItemBase {
    id: root
    implicitWidth: editing ? 32 : 0
    Rectangle { anchors.fill: parent; anchors.margins: 4; visible: root.editing; color: Appearance.colors.colLayer1; radius: Appearance.rounding.small }
    MaterialSymbol { anchors.centerIn: parent; text: "width_full"; iconSize: 18; color: Appearance.colors.colSubtext; visible: root.editing }
}
