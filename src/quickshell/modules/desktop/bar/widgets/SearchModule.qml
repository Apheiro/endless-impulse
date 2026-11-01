pragma ComponentBehavior: Bound
import QtQuick
import qs
import qs.services
import qs.modules.shared
import qs.modules.shared.primitives.common
import qs.modules.shared.primitives.bar
import qs.modules.desktop.bar

BarActionModuleBase {
    icon: "search"
    active: GlobalStates.overviewOpen
    onClicked: GlobalStates.overviewOpen = !GlobalStates.overviewOpen
}
