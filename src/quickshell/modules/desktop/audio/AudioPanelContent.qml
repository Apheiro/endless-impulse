pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets

ColumnLayout {
    id: root
    property bool embedded: false
    signal dismissed
    property string query: ""
    readonly property var groups: [
        {name: Translation.tr("Applications"), icon: "apps", sections: ["playback", "recording"]},
        {name: Translation.tr("Devices"), icon: "speaker", sections: ["outputs", "inputs", "profiles"]},
        {name: Translation.tr("Advanced"), icon: "tune", sections: ["routing", "advanced"]}
    ]
    readonly property var selectedGroup: groups.find(group => group.sections.includes(AudioControl.section)) || groups[0]
    readonly property var subpages: pages.filter(page => selectedGroup.sections.includes(page.id))
    readonly property var pages: [
        {
            id: "playback",
            name: Translation.tr("Playback"),
            icon: "play_circle"
        },
        {
            id: "recording",
            name: Translation.tr("Recording"),
            icon: "mic"
        },
        {
            id: "outputs",
            name: Translation.tr("Outputs"),
            icon: "speaker"
        },
        {
            id: "inputs",
            name: Translation.tr("Inputs"),
            icon: "settings_voice"
        },
        {
            id: "profiles",
            name: Translation.tr("Profiles"),
            icon: "tune"
        },
        {
            id: "routing",
            name: Translation.tr("Connections"),
            icon: "hub"
        },
        {
            id: "advanced",
            name: Translation.tr("Advanced"),
            icon: "data_object"
        }
    ]
    readonly property var audioModel: AudioControl.section === "outputs" ? AudioControl.outputs :
                                                                           AudioControl.section === "inputs"
                                                                           ? AudioControl.inputs :
                                                                             AudioControl.section
                                                                             === "recording"
                                                                             ? AudioControl.recording :
                                                                               AudioControl.playback
    spacing: 12
    RowLayout {
        Layout.fillWidth: true
        visible: !root.embedded
        MaterialSymbol {
            text: "graphic_eq"
            iconSize: 30
            color: Appearance.colors.colPrimary
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            StyledText {
                text: Translation.tr("Audio")
                font.pixelSize: Appearance.font.pixelSize.title
                font.weight: Font.DemiBold
            }
            StyledText {
                Layout.fillWidth: true
                text: AudioControl.server.name || "PipeWire"
                elide: Text.ElideRight
                color: Appearance.colors.colSubtext
                font.pixelSize: Appearance.font.pixelSize.smaller
            }
        }
        AudioRefreshButton {}
        RippleButton {
            implicitWidth: 34
            implicitHeight: 34
            onClicked: root.dismissed()
            contentItem: MaterialSymbol {
                text: "close"
                iconSize: 22
            }
            property var tooltip: StyledToolTip {
                text: Translation.tr("Close")
            }
        }
    }
    SegmentedControl {
        objectName: "audio-main-groups"
        Layout.fillWidth: true
        Layout.maximumWidth: 560
        model: root.groups
        currentIndex: Math.max(0, root.groups.findIndex(group => group.sections.includes(AudioControl.section)))
        onActivated: index => AudioControl.section = root.groups[index].sections[0]
    }
    SecondaryTabBar {
        objectName: "audio-subsections"
        Layout.fillWidth: true
        Layout.maximumWidth: 560
        currentIndex: Math.max(0, root.subpages.findIndex(page => page.id === AudioControl.section))
        onActivated: index => { if (index >= 0 && index < root.subpages.length) AudioControl.section = root.subpages[index].id; }
        Repeater {
            model: root.subpages
            delegate: SecondaryTabButton {
                required property var modelData
                buttonText: modelData.name
                implicitHeight: 36
                onClicked: AudioControl.section = modelData.id
            }
        }
    }
    RowLayout {
        objectName: "audio-device-defaults"
        visible: ["outputs", "inputs"].includes(AudioControl.section)
        Layout.fillWidth: true
        ColumnLayout {
            visible: AudioControl.section === "outputs"
            Layout.fillWidth: true
            StyledText {
                text: Translation.tr("System output")
                font.pixelSize: Appearance.font.pixelSize.smaller
                color: Appearance.colors.colSubtext
            }
            StyledComboBox {
                model: AudioControl.entries(AudioControl.outputs).filter(item => !item.processor
                                                                                 || item.default).map(item => (
                                                                                 {
                                                                                     name: item.name + (
                                                                                               item.processor
                                                                                               ? " · " + Translation.tr(
                                                                                                     "Virtual") :
                                                                                                 ""),
                                                                                     id: item.id,
                                                                                     serial: item.serial,
                                                                                     kind: item.kind,
                                                                                     default: item.default
                                                                                 }))
                textRole: "name"
                currentIndex: model.findIndex(item => item.default)
                onActivated: index => AudioControl.objectAction("default", model[index])
            }
        }
        ColumnLayout {
            visible: AudioControl.section === "inputs"
            Layout.fillWidth: true
            StyledText {
                text: Translation.tr("System input")
                font.pixelSize: Appearance.font.pixelSize.smaller
                color: Appearance.colors.colSubtext
            }
            StyledComboBox {
                model: AudioControl.entries(AudioControl.inputs).filter(item => (!item.monitor && !item.processor)
                       || item.default).map(item => ({
                    name: item.name + (item.processor ? " · " + Translation.tr("Virtual") : ""),
                    id: item.id,
                    serial: item.serial,
                    kind: item.kind,
                    default: item.default
                }))
                    textRole: "name"
                    currentIndex: model.findIndex(item => item.default)
                    onActivated: index => AudioControl.objectAction("default", model[index])
                }
            }
        }
        StyledText {
            objectName: "audio-processing-summary"
            Layout.fillWidth: true
            visible: ["outputs", "inputs"].includes(AudioControl.section) && AudioControl.entries(AudioControl.outputs).some(device => device.processor
                                                                               === "easyeffects")
            text: Translation.tr(
                      "EasyEffects processes application audio. System output selects the default destination; each application shows its actual route.")
            wrapMode: Text.WordWrap
            color: Appearance.colors.colSubtext
            font.pixelSize: Appearance.font.pixelSize.smaller
        }
        StyledText {
            Layout.fillWidth: true
            visible: ["outputs", "inputs"].includes(AudioControl.section) && [...AudioControl.entries(AudioControl.outputs), ...AudioControl.entries(
                    AudioControl.inputs)].some(device => device.default && device.processor)
            text: Translation.tr(
                      "An EasyEffects virtual device is currently the system default. Choose a physical device here so EasyEffects can follow it.")
            wrapMode: Text.WordWrap
            color: Appearance.colors.colPrimary
            font.pixelSize: Appearance.font.pixelSize.smaller
        }
        RowLayout {
            visible: ["playback", "recording", "outputs", "inputs"].includes(AudioControl.section)
            Layout.fillWidth: true
            MaterialTextField {
                Layout.fillWidth: true
                placeholderText: Translation.tr("Filter applications and devices…")
                onTextChanged: root.query = text
            }
            ConfigSwitch {
                Layout.fillWidth: false
                text: Translation.tr("Boost")
                checked: AudioControl.boost
                onCheckedChanged: AudioControl.boost = checked
            }
        }
        Flow {
            Layout.fillWidth: true
            visible: AudioControl.section === "inputs" || AudioControl.section === "recording"
            ConfigSwitch {
                text: Translation.tr("Monitor input levels")
                checked: AudioControl.inputMeters
                onCheckedChanged: AudioControl.inputMeters = checked
            }
            ConfigSwitch {
                visible: AudioControl.section === "inputs"
                text: Translation.tr("Show monitor sources")
                checked: AudioControl.showMonitors
                onCheckedChanged: AudioControl.showMonitors = checked
            }
        }
        StyledText {
            Layout.fillWidth: true
            visible: AudioControl.failed || !AudioControl.loaded
            text: AudioControl.failed ? AudioControl.message : Translation.tr("Connecting to PipeWire…")
            color: AudioControl.failed ? Appearance.m3colors.m3error : Appearance.colors.colSubtext
            wrapMode: Text.WordWrap
        }
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 1
            color: Appearance.colors.colOutlineVariant
        }
        StyledFlickable {
            id: scroll
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentHeight: content.implicitHeight + 8
            onWidthChanged: content.width = width
            ColumnLayout {
                id: content
                width: scroll.width
                spacing: 10
                Repeater {
                    model: ["playback", "recording", "outputs", "inputs"].includes(AudioControl.section)
                    ? root.audioModel : null
                    delegate: AudioNodeCard {
                        visible: (AudioControl.section !== "inputs" || AudioControl.showMonitors ||
                                  !entry.monitor) && (entry.name + " " + entry.media + " "
                                                      + entry.technicalName).toLowerCase().includes(
                                     root.query.toLowerCase())
                    }
                }
                StyledText {
                    visible: ["playback", "recording", "outputs", "inputs"].includes(AudioControl.section)
                    && root.audioModel.count === 0
                    Layout.fillWidth: true
                    Layout.topMargin: 24
                    text: AudioControl.section === "recording" ? Translation.tr(
                                                                     "No applications are recording audio") :
                                                                 AudioControl.section === "playback"
                                                                 ? Translation.tr(
                                                                       "Play audio in an application to manage its volume and destination") :
                                                                   Translation.tr("No devices available")
                    wrapMode: Text.WordWrap
                    color: Appearance.colors.colSubtext
                }
                Loader {
                    Layout.fillWidth: true
                    active: AudioControl.section === "profiles"
                    visible: active
                    sourceComponent: AudioProfiles {}
                }
                Loader {
                    Layout.fillWidth: true
                    active: AudioControl.section === "routing"
                    visible: active
                    sourceComponent: AudioRouting {}
                }
                Loader {
                    Layout.fillWidth: true
                    active: AudioControl.section === "advanced"
                    visible: active
                    sourceComponent: AudioAdvanced {}
                }
            }
        }
    }
