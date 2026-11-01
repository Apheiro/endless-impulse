pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import QtQuick.Dialogs
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets

ColumnLayout {
    id: root
    required property string label
    property alias text: input.text
    property alias placeholderText: input.placeholderText
    property alias validator: input.validator
    property bool secret: false
    property bool filePath: false
    Layout.fillWidth: true
    spacing: 4
    StyledText { Layout.fillWidth: true; text: root.label; wrapMode: Text.WordWrap; font.pixelSize: Appearance.font.pixelSize.small }
    RowLayout {
        Layout.fillWidth: true
        MaterialTextField { id: input; Layout.fillWidth: true; wrapMode: TextInput.NoWrap; echoMode: root.secret ? TextInput.Password : TextInput.Normal }
        RippleButtonWithIcon { visible: root.filePath; materialIcon: "folder_open"; mainText: ""; onClicked: { if (browser.item) browser.item.open(); else browser.active = true; } }
    }
    Loader {
        id: browser
        active: false
        onLoaded: item.open()
        sourceComponent: FileDialog {
            options: FileDialog.DontUseNativeDialog
            onAccepted: root.text = decodeURIComponent(selectedFile.toString().replace(/^file:\/\//, ""))
        }
    }
}
