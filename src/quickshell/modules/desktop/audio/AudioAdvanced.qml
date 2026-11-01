pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import Quickshell
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets

ColumnLayout {
    id: root
    objectName: "audio-advanced"
    Layout.fillWidth: true
    property string query: ""
    property string selectedId: ""
    readonly property var objects: AudioControl.graphObjects.filter(item => (item.name + " " + item.type + " "
                                                                            + item.id).toLowerCase().includes(
                                       query.toLowerCase()))
    readonly property var selected: AudioControl.graphObjects.find(item => item.id === selectedId)
    spacing: 12
    StyledText {
        Layout.fillWidth: true
        text: Translation.tr("Session clock")
        font.pixelSize: Appearance.font.pixelSize.larger
    }
    StyledText {
        Layout.fillWidth: true
        text: (AudioControl.clock["clock.rate"] || "—") + " Hz · " + (AudioControl.clock["clock.quantum"]
                                                                      || "—") + " " + Translation.tr("frames")
        color: Appearance.colors.colSubtext
    }
    RowLayout {
        Layout.fillWidth: true
        MaterialTextField {
            id: rate
            Layout.fillWidth: true
            Component.onCompleted: text = String(AudioControl.clock["clock.force-rate"] || 0)
            placeholderText: Translation.tr("Sample rate (Hz)")
        }
        RippleButtonWithIcon {
            materialIcon: "check"
            mainText: Translation.tr("Set rate")
            onClicked: AudioControl.perform({
                                                action: "clock",
                                                key: "clock.force-rate",
                                                value: Number(rate.text)
                                            })
        }
    }
    RowLayout {
        Layout.fillWidth: true
        MaterialTextField {
            id: quantum
            Layout.fillWidth: true
            Component.onCompleted: text = String(AudioControl.clock["clock.force-quantum"] || 0)
            placeholderText: Translation.tr("Quantum (frames)")
        }
        RippleButtonWithIcon {
            materialIcon: "check"
            mainText: Translation.tr("Set quantum")
            onClicked: AudioControl.perform({
                                                action: "clock",
                                                key: "clock.force-quantum",
                                                value: Number(quantum.text)
                                            })
        }
    }
    StyledText {
        Layout.fillWidth: true
        text: Translation.tr(
                  "0 restores automatic operation. Clock changes affect the entire audio session and may interrupt playback.")
        wrapMode: Text.WordWrap
        color: Appearance.colors.colSubtext
        font.pixelSize: Appearance.font.pixelSize.smaller
    }
    Rectangle {
        Layout.fillWidth: true
        implicitHeight: 1
        color: Appearance.colors.colOutlineVariant
    }
    StyledText {
        text: Translation.tr("PipeWire inspector")
        font.pixelSize: Appearance.font.pixelSize.larger
    }
    MaterialTextField {
        Layout.fillWidth: true
        placeholderText: Translation.tr("Find a node, device, client or module…")
        onTextChanged: root.query = text
    }
    StyledComboBox {
        model: root.objects.map(item => ({
            name: item.type + " · " + item.name + " #" + item.id,
            id: item.id
        }))
        textRole: "name"
        currentIndex: model.findIndex(item => item.id === root.selectedId)
        displayText: currentIndex < 0 ? Translation.tr("Select an object") : currentText
        onActivated: index => root.selectedId = model[index].id
    }
    RippleButtonWithIcon {
        visible: !!root.selected
        materialIcon: "content_copy"
        mainText: Translation.tr("Copy object details")
        onClicked: Quickshell.clipboardText = JSON.stringify(root.selected, null, 2)
    }
    StyledText {
        Layout.fillWidth: true
        visible: !!root.selected
        text: root.selected ? JSON.stringify(root.selected, null, 2) : ""
        wrapMode: Text.WrapAnywhere
        font.family: Appearance.font.family.monospace
        font.pixelSize: Appearance.font.pixelSize.smaller
        color: Appearance.colors.colSubtext
    }
}
