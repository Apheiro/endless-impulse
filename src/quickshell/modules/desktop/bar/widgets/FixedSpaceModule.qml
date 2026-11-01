pragma ComponentBehavior: Bound
import QtQuick
import qs
import qs.services
import qs.modules.shared
import qs.modules.shared.primitives.common
import qs.modules.shared.primitives.bar
import qs.modules.desktop.bar

BarLayoutItemBase {
    implicitWidth: spaceSize
    Rectangle { anchors.centerIn: parent; width: Math.max(1, Math.min(16, parent.width-4)); height: 2; color: Appearance.colors.colOutlineVariant; visible: parent.editing }
}
