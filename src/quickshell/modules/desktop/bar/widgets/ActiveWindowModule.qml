pragma ComponentBehavior: Bound
import QtQuick
import qs
import qs.services
import qs.modules.shared
import qs.modules.shared.primitives.common
import qs.modules.shared.primitives.bar
import qs.modules.desktop.bar

BarModuleBase {
    id: root
    contentWidthLimit: root.compact ? 100 : 200
    ActiveWindow { anchors.fill: parent; implicitWidth: root.compact ? 100 : 200 }
}
