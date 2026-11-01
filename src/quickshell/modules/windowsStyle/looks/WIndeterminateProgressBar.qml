import qs.modules.shared.primitives.common
import QtQuick
import Qt5Compat.GraphicalEffects
import qs
import qs.services
import qs.services.network
import qs.modules.shared
import qs.modules.shared.widgets
import qs.modules.windowsStyle.looks

StyledIndeterminateProgressBar {
    id: progressBar
    implicitHeight: 3
    background: null
    layer.enabled: true
    layer.effect: OpacityMask {
        maskSource: Rectangle {
            width: progressBar.width
            height: progressBar.height
            radius: progressBar.height / 2
        }
    }
}
