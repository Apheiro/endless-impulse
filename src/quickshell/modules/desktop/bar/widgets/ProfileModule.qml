pragma ComponentBehavior: Bound
import QtQuick
import qs
import qs.services
import qs.modules.shared
import qs.modules.shared.primitives.common
import qs.modules.shared.primitives.bar
import qs.modules.desktop.bar

import Quickshell.Services.UPower
BarActionModuleBase {
    icon: "bolt"
    label: compact ? "" : PowerProfiles.profile === PowerProfile.PowerSaver ? Translation.tr("Power saver") : PowerProfiles.profile === PowerProfile.Performance ? Translation.tr("Performance") : Translation.tr("Balanced")
    onClicked: PowerProfiles.profile = PowerProfiles.profile === PowerProfile.PowerSaver ? PowerProfile.Balanced : PowerProfiles.profile === PowerProfile.Balanced && PowerProfiles.hasPerformanceProfile ? PowerProfile.Performance : PowerProfile.PowerSaver
}
