pragma ComponentBehavior: Bound
import QtQuick
import qs
import qs.services
import qs.modules.shared
import qs.modules.shared.primitives.common
import qs.modules.shared.primitives.bar
import qs.modules.desktop.bar

BarActionModuleBase {
    icon: "system_update"
    label: Updates.available ? String(Updates.count) : "—"
    active: Updates.checking
    onClicked: Updates.refresh()
}
