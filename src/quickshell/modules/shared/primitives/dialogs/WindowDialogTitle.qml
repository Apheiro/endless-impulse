import qs.modules.shared.primitives.common
import QtQuick
import Quickshell
import qs.modules.shared
import qs.modules.shared.functions

StyledText {
    text: "Dialog Title"
    color: Appearance.colors.colOnSurface
    wrapMode: Text.Wrap
    font {
        family: Appearance.font.family.title
        pixelSize: Appearance.font.pixelSize.title
        variableAxes: Appearance.font.variableAxes.title
    }
}
