import QtQuick
import Quickshell
import qs.modules.shared
import qs.modules.windowsStyle.looks

WPopupToolTip {
    anchorEdges: Config.options.waffles.bar.bottom ? Edges.Top : Edges.Bottom
}
