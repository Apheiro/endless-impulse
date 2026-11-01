pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.settings
import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Widgets
import Quickshell.Services.Pipewire
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets

SettingsCard {
    id: root
    required property var entry
    objectName: "audio-node-card"
    property bool expanded: false
    property ListModel channelModel: ListModel {
        dynamicRoles: true
    }
    onEntryChanged: AudioControl.sync(channelModel, entry.channels.map(channel => Object.assign({}, channel, {
                                                                                                    id: channel.name,
                                                                                                    serial: channel.name
                                                                                                })))
    readonly property bool effectiveVolume: entry.volumeEffective !== false
    readonly property bool processing: entry.processor === "easyeffects"
    readonly property bool isDevice: entry.kind === "sink" || entry.kind === "source"
    readonly property bool isInput: entry.kind === "source" || entry.kind === "source-output"
    readonly property var targets: AudioControl.entries(isInput ? AudioControl.inputs : AudioControl.outputs)
    readonly property var nativeNode: Pipewire.nodes.values.find(node => node.id === entry.pwId) || null
    readonly property real maximum: {
        let limit = AudioControl.boost ? Math.min(200, Audio.hardMaxValue * 100) : 100;
        if (entry.default && entry.kind === "sink" && Config.options.audio.protection.enable)
            limit = Math.min(limit, Config.options.audio.protection.maxAllowed);
        return Math.max(entry.volume, limit);
    }
    Layout.fillWidth: true
    implicitHeight: body.implicitHeight + 28
    emphasized: entry.default
    PwObjectTracker {
        objects: root.nativeNode ? [root.nativeNode] : []
    }
    PwNodePeakMonitor {
        id: meter
        node: root.nativeNode
        enabled: AudioControl.opened && root.visible && (!root.isInput || AudioControl.inputMeters)
    }
    ColumnLayout {
        id: body
        anchors {
            left: parent.left
            right: parent.right
            top: parent.top
            margins: 14
        }
        spacing: 8
        RowLayout {
            Layout.fillWidth: true
            IconImage {
                visible: root.entry.icon.length > 0
                implicitSize: 28
                source: IconTheme.iconPath(root.entry.icon)
            }
            MaterialSymbol {
                visible: root.entry.icon.length === 0
                text: root.isInput ? "mic" : "speaker"
                iconSize: 25
                color: Appearance.colors.colPrimary
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                StyledText {
                    Layout.fillWidth: true
                    text: root.processing ? AudioControl.deviceLabel(root.entry, false) : root.entry.name
                    elide: Text.ElideRight
                    font.weight: Font.Medium
                }
                StyledText {
                    Layout.fillWidth: true
                    visible: text.length > 0
                    text: root.processing ? Translation.tr("Processing · virtual device") : root.entry.media
                                            || root.entry.format
                    elide: Text.ElideRight
                    color: Appearance.colors.colSubtext
                    font.pixelSize: Appearance.font.pixelSize.smaller
                }
            }
            RippleButton {
                visible: root.isDevice && !root.processing
                implicitWidth: 32
                implicitHeight: 32
                onClicked: AudioControl.objectAction("default", root.entry)
                contentItem: MaterialSymbol {
                    text: root.entry.default ? "star" : "star_outline"
                    iconSize: 20
                    color: root.entry.default ? Appearance.colors.colPrimary : Appearance.colors.colSubtext
                }
                property var tooltip: StyledToolTip {
                    text: Translation.tr("Use as default device")
                }
            }
            RippleButton {
                implicitWidth: 32
                implicitHeight: 32
                visible: root.effectiveVolume
                onClicked: AudioControl.objectAction("mute", root.entry, !root.entry.muted)
                contentItem: MaterialSymbol {
                    text: root.isInput ? (root.entry.muted ? "mic_off" : "mic") : (root.entry.muted
                                                                                   ? "volume_off" :
                                                                                     "volume_up")
                    iconSize: 21
                    color: root.entry.muted ? Appearance.colors.colSubtext : Appearance.colors.colOnLayer0
                }
                property var tooltip: StyledToolTip {
                    text: root.entry.muted ? Translation.tr("Unmute") : Translation.tr("Mute")
                }
            }
            RippleButton {
                implicitWidth: 28
                implicitHeight: 32
                onClicked: root.expanded = !root.expanded
                contentItem: MaterialSymbol {
                    text: root.expanded ? "expand_less" : "expand_more"
                    iconSize: 20
                }
                property var tooltip: StyledToolTip {
                    text: Translation.tr("Channels and details")
                }
            }
        }
        RowLayout {
            objectName: "audio-master-volume"
            visible: root.effectiveVolume
            Layout.fillWidth: true
            StyledSlider {
                id: volume
                Layout.fillWidth: true
                from: 0
                to: root.maximum
                stepSize: 1
                configuration: StyledSlider.Configuration.S
                usePercentTooltip: false
                tooltipContent: Math.round(value) + "%"
                stopIndicatorValues: [100]
                onMoved: AudioControl.objectAction("volume", root.entry, Math.round(value))
                Binding {
                    target: volume
                    property: "value"
                    value: AudioControl.previewVolume(root.entry, -1)
                    when: !volume.pressed
                }
            }
            StyledText {
                Layout.preferredWidth: 48
                text: Math.round(volume.value) + "%"
                horizontalAlignment: Text.AlignRight
                font.family: Appearance.font.family.numbers
                font.pixelSize: Appearance.font.pixelSize.small
            }
        }
        StyledText {
            objectName: "audio-virtual-volume-hint"
            Layout.fillWidth: true
            visible: !root.effectiveVolume
            text: Translation.tr(
                      "This virtual device bypasses its volume control. Adjust the final output device.")
            wrapMode: Text.WordWrap
            color: Appearance.colors.colSubtext
            font.pixelSize: Appearance.font.pixelSize.smaller
        }
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 3
            radius: 2
            visible: meter.enabled
            color: Appearance.colors.colLayer2Base
            Rectangle {
                width: parent.width * Math.min(1, meter.peak)
                height: parent.height
                radius: 2
                color: meter.peak > 0.95 ? Appearance.m3colors.m3error : Appearance.colors.colPrimary
            }
        }
        StyledComboBox {
            Layout.fillWidth: true
            visible: !root.isDevice
            model: root.targets.map(target => ({
                name: AudioControl.deviceLabel(target, root.targets.some(device => device.processor
                                                                                   === "easyeffects")),
                id: target.id,
                serial: target.serial
            }))
            textRole: "name"
            currentIndex: model.findIndex(target => target.id === root.entry.target)
            displayText: currentIndex < 0 ? Translation.tr("Choose device") : currentText
            onActivated: index => AudioControl.perform({
                                                           action: "move",
                                                           kind: root.entry.kind,
                                                           id: root.entry.id,
                                                           serial: root.entry.serial,
                                                           target: model[index].id,
                                                           targetSerial: model[index].serial
                                                       })
        }
        StyledComboBox {
            visible: root.isDevice && root.entry.ports.length > 0
            model: root.entry.ports.filter(port => port.available !== "no" || port.name
                                                   === root.entry.activePort)
            textRole: "label"
            currentIndex: model.findIndex(port => port.name === root.entry.activePort)
            onActivated: index => AudioControl.objectAction("port", root.entry, model[index].name)
        }
        ColumnLayout {
            Layout.fillWidth: true
            visible: root.expanded
            Repeater {
                model: root.effectiveVolume ? root.channelModel : null
                delegate: RowLayout {
                    id: channel
                    required property var entry
                    required property int index
                    Layout.fillWidth: true
                    StyledText {
                        Layout.preferredWidth: 100
                        text: channel.entry.name
                        elide: Text.ElideRight
                        font.pixelSize: Appearance.font.pixelSize.smaller
                    }
                    StyledSlider {
                        id: channelSlider
                        Layout.fillWidth: true
                        from: 0
                        to: root.maximum
                        stepSize: 1
                        Binding {
                            target: channelSlider
                            property: "value"
                            value: AudioControl.previewVolume(root.entry, channel.index)
                            when: !channelSlider.pressed
                        }
                        configuration: StyledSlider.Configuration.XS
                        usePercentTooltip: false
                        tooltipContent: Math.round(value) + "%"
                        onMoved: {
                            const values = root.entry.channels.map((c, index) => AudioControl.previewVolume(root.entry, index));
                            values[channel.index] = Math.round(value);
                            AudioControl.perform({
                                                     action: "volume",
                                                     kind: root.entry.kind,
                                                     id: root.entry.id,
                                                     serial: root.entry.serial,
                                                     values: values
                                                 });
                        }
                    }
                    StyledText {
                        Layout.preferredWidth: 40
                        text: Math.round(channelSlider.value) + "%"
                        font.pixelSize: Appearance.font.pixelSize.smaller
                    }
                }
            }
            StyledText {
                Layout.fillWidth: true
                text: root.entry.technicalName || root.entry.format
                wrapMode: Text.WrapAnywhere
                color: Appearance.colors.colSubtext
                font.pixelSize: Appearance.font.pixelSize.smaller
            }
        }
    }
}
