pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.settings
import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets

ColumnLayout {
    Layout.fillWidth: true
    Repeater {
        model: AudioControl.cards
        delegate: SettingsCard {
            id: card
            required property var entry
            objectName: "audio-profile-card"
            property bool details: false
            property ListModel portModel: ListModel {
                dynamicRoles: true
            }
            onEntryChanged: AudioControl.sync(portModel, entry.ports.map(port => Object.assign({}, port, {
                                                                                                   id: port.name,
                                                                                                   serial: port.name
                                                                                               })))
            Layout.fillWidth: true
            implicitHeight: body.implicitHeight + 28
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
                    text: card.entry.name
                    font.weight: Font.Medium
                    wrapMode: Text.WordWrap
                }
                StyledComboBox {
                    model: card.entry.profiles.filter(profile => profile.available !== "no" || profile.name
                                                                 === card.entry.activeProfile)
                    textRole: "label"
                    currentIndex: model.findIndex(profile => profile.name === card.entry.activeProfile)
                    onActivated: index => AudioControl.perform({
                                                                   action: "profile",
                                                                   kind: "card",
                                                                   id: card.entry.id,
                                                                   serial: card.entry.serial,
                                                                   value: model[index].name
                                                               })
                }
                RippleButtonWithIcon {
                    materialIcon: card.details ? "expand_less" : "tune"
                    mainText: Translation.tr("Port latency offsets")
                    onClicked: card.details = !card.details
                }
                Repeater {
                    model: card.details ? card.portModel : null
                    delegate: RowLayout {
                        id: port
                        required property var entry
                        Layout.fillWidth: true
                        StyledText {
                            Layout.fillWidth: true
                            text: port.entry.label
                            wrapMode: Text.WordWrap
                            font.pixelSize: Appearance.font.pixelSize.small
                        }
                        MaterialTextField {
                            id: latency
                            Layout.preferredWidth: 100
                            Component.onCompleted: text = String(port.entry.latency / 1000)
                            placeholderText: "ms"
                        }
                        StyledText {
                            text: "ms"
                            color: Appearance.colors.colSubtext
                        }
                        RippleButtonWithIcon {
                            materialIcon: "check"
                            mainText: Translation.tr("Apply")
                            onClicked: AudioControl.perform({
                                                                action: "latency",
                                                                kind: "card",
                                                                id: card.entry.id,
                                                                serial: card.entry.serial,
                                                                port: port.entry.name,
                                                                value: Number(latency.text) * 1000
                                                            })
                        }
                    }
                }
            }
        }
    }
    StyledText {
        visible: AudioControl.cards.count === 0
        Layout.fillWidth: true
        text: Translation.tr("No audio cards available")
        color: Appearance.colors.colSubtext
    }
}
