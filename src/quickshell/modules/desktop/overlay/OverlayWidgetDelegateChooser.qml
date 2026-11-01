pragma ComponentBehavior: Bound
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets
import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Bluetooth
import qs.modules.desktop.overlay.crosshair
import qs.modules.desktop.overlay.volumeMixer
import qs.modules.desktop.overlay.floatingImage
import qs.modules.desktop.overlay.fpsLimiter
import qs.modules.desktop.overlay.recorder
import qs.modules.desktop.overlay.resources
import qs.modules.desktop.overlay.notes

DelegateChooser {
    id: root
    role: "identifier"

    DelegateChoice { roleValue: "crosshair"; Crosshair {} }
    DelegateChoice { roleValue: "floatingImage"; FloatingImage {} }
    DelegateChoice { roleValue: "fpsLimiter"; FpsLimiter {} }
    DelegateChoice { roleValue: "recorder"; Recorder {} }
    DelegateChoice { roleValue: "resources"; Resources {} }
    DelegateChoice { roleValue: "notes"; Notes {} }
    DelegateChoice { roleValue: "volumeMixer"; VolumeMixer {} }
}
