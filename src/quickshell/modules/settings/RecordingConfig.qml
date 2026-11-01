pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import Quickshell
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets

SettingsPage {
    id: root
    property var draft: ({})
    property bool dirty: false
    property bool advanced: false
    readonly property var groups: [...new Set(ScreenRecorder.fields.map(field => field.group))]
    function reset() { draft = JSON.parse(JSON.stringify(ScreenRecorder.settings)); dirty = false; }
    function put(key, value) { draft = Object.assign({}, draft, {[key]: value}); dirty = true; }
    Component.onCompleted: { if (ScreenRecorder.loaded) reset(); else ScreenRecorder.refresh(); }
    Connections { target: ScreenRecorder; function onSettingsChanged() { if (!root.dirty) root.reset(); } function onPreferencesSaved() { root.reset(); } }

    SettingsSection {
        icon: "videocam"
        title: "GPU Screen Recorder"
        StyledText {
            Layout.fillWidth: true
            text: ScreenRecorder.capabilities.installed ? Translation.tr("Installed version: ") + ScreenRecorder.capabilities.version : Translation.tr("GPU Screen Recorder is not installed")
            wrapMode: Text.WordWrap
        }
        Flow {
            Layout.fillWidth: true
            spacing: 6
            RippleButtonWithIcon {
                materialIcon: "save"; mainText: Translation.tr("Save preferences")
                enabled: root.dirty && !ScreenRecorder.busy
                onClicked: ScreenRecorder.save(root.draft)
            }
            RippleButtonWithIcon {
                materialIcon: "undo"; mainText: Translation.tr("Discard")
                enabled: root.dirty && !ScreenRecorder.busy
                onClicked: root.reset()
            }
            RippleButtonWithIcon {
                materialIcon: "refresh"; mainText: Translation.tr("Refresh devices")
                enabled: !ScreenRecorder.busy
                onClicked: ScreenRecorder.refresh()
            }
            RippleButtonWithIcon {
                materialIcon: ScreenRecorder.active ? "stop" : "fiber_manual_record"
                mainText: ScreenRecorder.active ? Translation.tr("Stop recording") : Translation.tr("Start saved configuration")
                enabled: !ScreenRecorder.busy && ScreenRecorder.capabilities.installed && !root.dirty
                onClicked: ScreenRecorder.toggle()
            }
        }
        StyledText {
            Layout.fillWidth: true
            text: ScreenRecorder.message
            visible: text.length > 0
            color: ScreenRecorder.failed ? Appearance.m3colors.m3error : Appearance.colors.colSubtext
            wrapMode: Text.WordWrap
        }
    }
    RippleButtonWithIcon {
        materialIcon: root.advanced ? "expand_less" : "expand_more"
        mainText: Translation.tr("Capture, replay, streaming & advanced options")
        onClicked: root.advanced = !root.advanced
    }
    Repeater {
        model: root.groups
        delegate: SettingsSection {
            id: group
            required property string modelData
            visible: ["Files", "Video", "Audio"].includes(modelData) || root.advanced
            title: Translation.tr(modelData)
            icon: ({Files:"folder", Video:"movie", Audio:"volume_up", Capture:"screenshot_region", "Replay & streaming":"replay", "Encoding & color":"memory", Advanced:"tune"})[modelData]
            Repeater {
                model: ScreenRecorder.fields.filter(field => field.group === group.modelData)
                delegate: RecorderField {
                    required property var modelData
                    field: modelData
                    value: root.draft[modelData.key] ?? modelData.default
                    onEdited: value => root.put(modelData.key, value)
                }
            }
            ColumnLayout {
                Layout.fillWidth: true
                visible: group.modelData === "Files"
                RippleButtonWithIcon {
                    materialIcon: "preview"; mainText: Translation.tr("Preview filename")
                    enabled: !ScreenRecorder.busy
                    onClicked: ScreenRecorder.previewName(root.draft)
                }
                StyledText {
                    Layout.fillWidth: true
                    text: ScreenRecorder.preview
                    wrapMode: Text.WrapAnywhere
                    font.pixelSize: Appearance.font.pixelSize.smaller
                    color: Appearance.colors.colSubtext
                }
            }
            ColumnLayout {
                Layout.fillWidth: true
                visible: group.modelData === "Audio"
                StyledComboBox {
                    id: source
                    model: ScreenRecorder.capabilities.audio.concat(ScreenRecorder.capabilities.applications.map(app => ({id: "app:" + app.id, name: app.name})))
                    textRole: "name"
                }
                RippleButtonWithIcon {
                    materialIcon: "add"; mainText: Translation.tr("Add as separate audio track")
                    enabled: source.currentIndex >= 0
                    onClicked: root.put("audioTracks", [...(root.draft.audioTracks || []), source.model[source.currentIndex].id])
                }
            }
            StyledText {
                Layout.fillWidth: true
                visible: group.modelData === "Capture"
                text: Translation.tr("Capture sources: ") + ScreenRecorder.capabilities.capture.map(item => item.id).join(" · ")
                wrapMode: Text.WordWrap
                font.pixelSize: Appearance.font.pixelSize.smaller
                color: Appearance.colors.colSubtext
            }
        }
    }
    EnvironmentPaths {
        entries: [{name: "GPU Screen Recorder", path: ScreenRecorder.store, exists: ScreenRecorder.preferencesExist}, {name: Translation.tr("Recording state & log"), path: ScreenRecorder.statePath, exists: ScreenRecorder.loaded}]
    }
}
