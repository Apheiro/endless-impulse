pragma ComponentBehavior: Bound
import QtQuick
import qs
import qs.services
import qs.modules.shared
import qs.modules.shared.primitives.common
import qs.modules.shared.primitives.bar
import qs.modules.desktop.bar

BarLayoutItemBase {
    implicitWidth: 12
    BarSeparator { anchors.centerIn: parent; height: parent.height }
}
