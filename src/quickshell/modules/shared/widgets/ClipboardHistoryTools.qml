import QtQuick
import QtQuick.Layouts
import qs.services
import qs.modules.shared
import qs.modules.shared.primitives.common

ColumnLayout {
    Component.onCompleted: Cliphist.refresh()
    spacing: 4
    RowLayout {
        Layout.fillWidth: true
        spacing: 8
        StyledText {
            Layout.fillWidth: true
            text: Translation.tr("Saved items are kept") + " · " + Cliphist.pinned.length
            font.pixelSize: Appearance.font.pixelSize.smaller
            color: Appearance.colors.colSubtext
        }
        RippleButtonWithIcon {
            objectName: "clipboard-clear-history"
            materialIcon: "delete_sweep"
            mainText: Translation.tr("Clear history")
            enabled: !Cliphist.busy && Cliphist.removableCount > 0
            onClicked: Cliphist.clearUnpinned()
        }
    }
    StyledText {
        Layout.fillWidth: true
        visible: Cliphist.error.length > 0
        text: Cliphist.error
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: Appearance.colors.colError
        font.pixelSize: Appearance.font.pixelSize.smaller
    }
}
