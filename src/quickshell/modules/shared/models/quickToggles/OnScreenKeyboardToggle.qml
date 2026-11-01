import QtQuick
import Quickshell
import qs
import qs.services
import qs.modules.shared
import qs.modules.shared.functions
import qs.modules.shared.widgets

QuickToggleModel {
    name: Translation.tr("Virtual Keyboard")
    toggled: GlobalStates.oskOpen
    icon: toggled ? "keyboard_hide" : "keyboard"
    
    mainAction: () => {
        GlobalStates.oskOpen = !GlobalStates.oskOpen
    }

    tooltipText: Translation.tr("On-screen keyboard")
}
