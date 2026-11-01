pragma ComponentBehavior: Bound
import QtQuick
import qs
import qs.services
import qs.modules.shared
import qs.modules.shared.primitives.common
import qs.modules.shared.primitives.bar
import qs.modules.desktop.bar

BarActionModuleBase {
    icon: "power_settings_new"
    active: GlobalStates.sessionOpen
    onClicked: GlobalStates.sessionOpen = !GlobalStates.sessionOpen
}
