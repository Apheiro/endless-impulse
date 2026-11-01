import QtQuick
import Quickshell
import qs
import qs.services
import qs.modules.shared
import qs.modules.shared.functions
import qs.modules.shared.widgets

QuickToggleModel {
    name: Translation.tr("Keep awake")

    toggled: Idle.inhibit
    icon: "coffee"
    mainAction: () => {
        Idle.toggleInhibit()
    }
    tooltipText: Translation.tr("Keep system awake")
}
