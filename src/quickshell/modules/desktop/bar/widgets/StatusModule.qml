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
    active: GlobalStates.sidebarRightOpen || QuickPanelState.section !== ""
    BarStatusGroup { anchors.fill: parent; surfaceVisible: false }
}
