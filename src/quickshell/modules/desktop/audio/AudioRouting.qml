pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets

ColumnLayout {
    id: root
    property bool allMedia: false
    property bool passive: false
    property string outputId: ""
    property string inputId: ""
    readonly property var outputs: AudioControl.ports.filter(port => port.direction === "out" && (allMedia || port.media.toLowerCase(
                                                                                                      ).includes(
                                                                                                      "audio")
                                                                                                  || port.channel.length
                                                                                                  > 0))
    readonly property var inputs: AudioControl.ports.filter(port => port.direction === "in" && (allMedia
                                                                                                || port.media.toLowerCase(
                                                                                                    ).includes(
                                                                                                    "audio")
                                                                                                || port.channel.length
                                                                                                > 0))
    Layout.fillWidth: true
    spacing: 12
    StyledText {
        Layout.fillWidth: true
        text: Translation.tr(
                  "Connect individual PipeWire ports. Application device selection is available in Playback and Recording.")
        wrapMode: Text.WordWrap
        color: Appearance.colors.colSubtext
    }
    ConfigSwitch {
        text: Translation.tr("Include MIDI, video and other media ports")
        checked: root.allMedia
        onCheckedChanged: root.allMedia = checked
    }
    StyledText {
        text: Translation.tr("Output port")
        font.pixelSize: Appearance.font.pixelSize.small
    }
    StyledComboBox {
        id: output
        model: root.outputs
        textRole: "name"
        currentIndex: model.findIndex(port => port.id === root.outputId)
        onActivated: index => root.outputId = model[index].id
        displayText: currentIndex < 0 ? Translation.tr("Choose output port") : currentText
    }
    StyledText {
        text: Translation.tr("Input port")
        font.pixelSize: Appearance.font.pixelSize.small
    }
    StyledComboBox {
        id: input
        model: root.inputs
        textRole: "name"
        currentIndex: model.findIndex(port => port.id === root.inputId)
        onActivated: index => root.inputId = model[index].id
        displayText: currentIndex < 0 ? Translation.tr("Choose input port") : currentText
    }
    RowLayout {
        Layout.fillWidth: true
        ConfigSwitch {
            Layout.fillWidth: true
            text: Translation.tr("Passive connection")
            checked: root.passive
            onCheckedChanged: root.passive = checked
        }
        RippleButtonWithIcon {
            materialIcon: "add_link"
            mainText: Translation.tr("Connect")
            enabled: output.currentIndex >= 0 && input.currentIndex >= 0
            onClicked: {
                const from = root.outputs[output.currentIndex], to = root.inputs[input.currentIndex];
                AudioControl.perform({
                                         action: "connect",
                                         output: from.id,
                                         outputSerial: from.serial,
                                         input: to.id,
                                         inputSerial: to.serial,
                                         passive: root.passive
                                     });
            }
        }
    }
    Rectangle {
        Layout.fillWidth: true
        implicitHeight: 1
        color: Appearance.colors.colOutlineVariant
    }
    Repeater {
        model: AudioControl.links
        delegate: RowLayout {
            id: linkRow
            required property var entry
            Layout.fillWidth: true
            ColumnLayout {
                Layout.fillWidth: true
                StyledText {
                    Layout.fillWidth: true
                    text: linkRow.entry.outputName
                    elide: Text.ElideRight
                    font.pixelSize: Appearance.font.pixelSize.small
                }
                StyledText {
                    Layout.fillWidth: true
                    text: "→ " + linkRow.entry.inputName
                    elide: Text.ElideRight
                    font.pixelSize: Appearance.font.pixelSize.smaller
                    color: Appearance.colors.colSubtext
                }
            }
            RippleButton {
                implicitWidth: 32
                implicitHeight: 32
                onClicked: AudioControl.perform({
                                                    action: "disconnect",
                                                    id: linkRow.entry.id,
                                                    serial: linkRow.entry.serial
                                                })
                contentItem: MaterialSymbol {
                    text: "link_off"
                    iconSize: 20
                }
                property var tooltip: StyledToolTip {
                    text: Translation.tr("Disconnect ports")
                }
            }
        }
    }
}
