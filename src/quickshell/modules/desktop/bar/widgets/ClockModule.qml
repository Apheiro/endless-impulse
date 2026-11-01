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

    ClockWidget { anchors.fill: parent; showDate: Config.options.bar.verbose && !root.compact }
}
