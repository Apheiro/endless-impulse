pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets

Rectangle {
    id: root
    readonly property var request: BluetoothManager.prompt
    readonly property bool input: request.kind === "RequestPinCode" || request.kind === "RequestPasskey"
    readonly property bool display: request.kind?.startsWith("Display") ?? false
    Layout.fillWidth: true
    implicitHeight: body.implicitHeight + 28
    color: Appearance.colors.colLayer0
    radius: Appearance.rounding.normal
    border.width: 1
    border.color: Appearance.colors.colPrimary
    onRequestChanged: Qt.callLater(() => {
        if (code) {
            code.text = "";
            if (root.input)
                code.forceActiveFocus();
        }
    })
    ColumnLayout {
        id: body
        anchors {
            left: parent.left
            right: parent.right
            top: parent.top
            margins: 14
        }
        spacing: 10
        StyledText {
            Layout.fillWidth: true
            text: Translation.tr("Pairing with ") + BluetoothManager.nameFor(root.request.device || "")
            textFormat: Text.PlainText
            font.weight: Font.DemiBold
            elide: Text.ElideRight
        }
        StyledText {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            color: Appearance.colors.colSubtext
            text: root.display ? Translation.tr("Enter this code on the other device, then press Enter.") :
                                 root.input ? Translation.tr(
                                                  "Enter the PIN or passkey shown on the other device.") :
                                              root.request.kind === "RequestConfirmation" ? Translation.tr(
                                                                                                "Does this code match the one shown on the other device?") :
                                                                                            Translation.tr(
                                                                                                "Allow this Bluetooth pairing or service request?")
        }
        StyledText {
            visible: !!root.request.code
            text: root.request.code || ""
            font.family: Appearance.font.family.numbers
            font.pixelSize: 30
            color: Appearance.colors.colPrimary
        }
        StyledText {
            visible: root.request.kind === "DisplayPasskey"
            text: Translation.tr("Digits entered: ") + (root.request.entered || 0)
            color: Appearance.colors.colSubtext
        }
        StyledText {
            visible: !!root.request.service
            Layout.fillWidth: true
            text: root.request.service || ""
            wrapMode: Text.WrapAnywhere
            font.pixelSize: Appearance.font.pixelSize.smaller
            color: Appearance.colors.colSubtext
        }
        MaterialTextField {
            id: code
            Layout.fillWidth: true
            visible: root.input
            maximumLength: root.request.kind === "RequestPasskey" ? 6 : 16
            inputMethodHints: root.request.kind === "RequestPasskey" ? Qt.ImhDigitsOnly : Qt.ImhNone
            placeholderText: Translation.tr("PIN / passkey")
            onAccepted: if (text.length)
                            BluetoothManager.respond(true, text)
        }
        RowLayout {
            RippleButtonWithIcon {
                materialIcon: "close"
                mainText: Translation.tr("Reject")
                onClicked: {
                    if (root.display)
                        BluetoothManager.command("cancel", root.request.device);
                    else
                        BluetoothManager.respond(false, "");
                }
            }
            RippleButtonWithIcon {
                visible: !root.display
                materialIcon: "check"
                mainText: Translation.tr("Confirm")
                enabled: !root.input || code.text.length > 0
                onClicked: BluetoothManager.respond(true, code.text)
            }
        }
    }
}
