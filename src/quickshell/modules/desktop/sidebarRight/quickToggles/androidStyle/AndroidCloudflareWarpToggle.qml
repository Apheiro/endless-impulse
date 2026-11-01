import qs.modules.shared
import qs.modules.shared.models.quickToggles
import qs.modules.shared.widgets
import qs.services
import QtQuick
import Quickshell
import Quickshell.Io

AndroidQuickToggleButton {
    id: root

    toggleModel: CloudflareWarpToggle {}
}
