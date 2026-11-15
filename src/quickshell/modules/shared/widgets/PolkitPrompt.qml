pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import qs.services
import qs.modules.shared
import qs.modules.shared.primitives.common
import qs.modules.shared.primitives.dialogs

FocusScope {
    id: root
    implicitHeight: column.implicitHeight + 2 * Appearance.rounding.large
    function submit() {
        // The field is cleared before entering the backend. Never send via IPC.
        const response = input.text;
        input.clear();
        PolkitService.submit(response);
    }
    Keys.onEscapePressed: event => { PolkitService.cancel(); event.accepted = true; }
    Connections {
        target: PolkitService
        function onClearInput() {
            input.clear();
            if (PolkitService.interactionAvailable) Qt.callLater(() => input.forceActiveFocus());
        }
    }
    Component.onCompleted: { input.clear(); input.forceActiveFocus(); }
    Component.onDestruction: input.clear()
    ScrollView {
        anchors.fill: parent
        anchors.margins: Appearance.rounding.large
        contentWidth: availableWidth
        clip: true
        ColumnLayout {
            id: column
            width: parent.width
            spacing: Appearance.rounding.medium
            RowLayout {
                Layout.fillWidth: true
                MaterialSymbol { text: "security"; color: Appearance.colors.colPrimary }
                WindowDialogTitle { Layout.fillWidth: true; text: Translation.tr("Authentication") }
            }
            WindowDialogParagraph {
                Layout.fillWidth: true
                text: PolkitService.cleanMessage
                color: Appearance.colors.colOnLayer0
                textFormat: Text.PlainText
            }
            StyledComboBox {
                id: identities
                Layout.fillWidth: true
                visible: count > 1
                model: Array.from(PolkitService.flow?.identities ?? [])
                textRole: "displayName"
                currentIndex: model.indexOf(PolkitService.flow?.selectedIdentity)
                onActivated: PolkitService.selectIdentity(model[index])
                Accessible.name: Translation.tr("Identity")
            }
            WindowDialogParagraph {
                Layout.fillWidth: true
                objectName: "polkit-feedback"
                visible: text.length > 0
                text: PolkitService.feedback
                textFormat: Text.PlainText
                color: PolkitService.flow?.supplementaryIsError || PolkitService.flow?.failed ? Appearance.colors.colError : Appearance.colors.colOnLayer0
                Accessible.role: Accessible.AlertMessage
            }
            StyledText {
                Layout.fillWidth: true
                text: PolkitService.cleanPrompt
                color: Appearance.colors.colOnLayer0
                wrapMode: Text.Wrap
                textFormat: Text.PlainText
            }
            MaterialTextField {
                id: input
                objectName: "polkit-response"
                Layout.fillWidth: true
                enabled: PolkitService.interactionAvailable
                wrapMode: TextInput.NoWrap
                echoMode: PolkitService.flow?.responseVisible ? TextInput.Normal : TextInput.Password
                inputMethodHints: Qt.ImhNoPredictiveText | Qt.ImhNoAutoUppercase | Qt.ImhSensitiveData
                Accessible.name: PolkitService.cleanPrompt
                onAccepted: root.submit()
            }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                DialogButton { buttonText: Translation.tr("Cancel"); onClicked: PolkitService.cancel() }
                DialogButton { buttonText: Translation.tr("Continue"); enabled: PolkitService.interactionAvailable; onClicked: root.submit() }
            }
        }
    }
}
