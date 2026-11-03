pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.common
import qs.modules.shared.primitives.settings
import QtQuick
import QtQuick.Layouts
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets
import "RecordingLayout.js" as RecordingLayout

Item {
    id: root
    property var draft: ({})
    property bool dirty: false
    property int currentTab: 0
    readonly property var tabs: [
        {name: Translation.tr("Session"), icon: "videocam"},
        {name: Translation.tr("Video"), icon: "movie"},
        {name: Translation.tr("Audio"), icon: "volume_up"},
        {name: Translation.tr("Advanced"), icon: "tune"}
    ]
    readonly property var groups: RecordingLayout.groupsForTab(ScreenRecorder.fields, currentTab)

    function reset() {
        draft = JSON.parse(JSON.stringify(ScreenRecorder.settings));
        dirty = false;
    }
    function put(key, value) {
        draft = Object.assign({}, draft, {[key]: value});
        dirty = true;
    }
    Component.onCompleted: {
        if (ScreenRecorder.loaded) reset();
        else ScreenRecorder.refresh();
    }
    Connections {
        target: ScreenRecorder
        function onSettingsChanged() { if (!root.dirty) root.reset(); }
        function onPreferencesSaved() { root.reset(); }
    }
    onCurrentTabChanged: page.contentY = 0

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 12

        SettingsCard {
            Layout.fillWidth: true
            implicitHeight: sessionHeader.implicitHeight + 32

            ColumnLayout {
                id: sessionHeader
                anchors { left: parent.left; right: parent.right; top: parent.top; margins: 16 }
                spacing: 12

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 12
                    MaterialSymbol {
                        text: ScreenRecorder.active ? "radio_button_checked" : "videocam"
                        iconSize: Appearance.font.pixelSize.huge
                        color: Appearance.colors.colPrimary
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        spacing: 2
                        StyledText {
                            Layout.fillWidth: true
                            text: ScreenRecorder.active
                                ? (ScreenRecorder.paused ? Translation.tr("Paused") : Translation.tr("Recording")) + " · " + ScreenRecorder.elapsedText
                                : "GPU Screen Recorder"
                            font.pixelSize: Appearance.font.pixelSize.larger
                            font.weight: Font.DemiBold
                            wrapMode: Text.WordWrap
                        }
                        StyledText {
                            Layout.fillWidth: true
                            text: ScreenRecorder.capabilities.installed
                                ? Translation.tr("Installed version: ") + ScreenRecorder.capabilities.version
                                : Translation.tr("GPU Screen Recorder is not installed")
                            color: Appearance.colors.colSubtext
                            font.pixelSize: Appearance.font.pixelSize.smaller
                            wrapMode: Text.WordWrap
                        }
                    }
                    ActionButton {
                        materialIcon: "refresh"
                        mainText: ""
                        Accessible.name: Translation.tr("Refresh devices")
                        enabled: !ScreenRecorder.busy
                        onClicked: ScreenRecorder.refresh()
                        StyledToolTip { text: Translation.tr("Refresh devices") }
                    }
                }
                Flow {
                    id: actions
                    Layout.fillWidth: true
                    spacing: 8
                    ActionButton {
                        objectName: "recorder-session-action"
                        width: Math.min(implicitWidth, actions.width)
                        toggled: true
                        materialIcon: ScreenRecorder.active ? "stop" : "fiber_manual_record"
                        mainText: ScreenRecorder.active ? Translation.tr("Stop recording") : Translation.tr("Start saved configuration")
                        // Stopping must remain available while a preferences draft exists.
                        enabled: !ScreenRecorder.busy && (ScreenRecorder.active || (ScreenRecorder.capabilities.installed && !root.dirty))
                        onClicked: ScreenRecorder.toggle()
                    }
                    ActionButton {
                        objectName: "recorder-save"
                        width: Math.min(implicitWidth, actions.width)
                        materialIcon: "save"
                        mainText: Translation.tr("Save preferences")
                        enabled: root.dirty && !ScreenRecorder.busy
                        onClicked: ScreenRecorder.save(root.draft)
                    }
                    ActionButton {
                        objectName: "recorder-discard"
                        width: Math.min(implicitWidth, actions.width)
                        materialIcon: "undo"
                        mainText: Translation.tr("Discard")
                        enabled: root.dirty && !ScreenRecorder.busy
                        onClicked: root.reset()
                    }
                }
                StyledText {
                    Layout.fillWidth: true
                    visible: root.dirty || ScreenRecorder.message.length > 0
                    text: (root.dirty ? Translation.tr("Unsaved changes") + (ScreenRecorder.message ? " · " : "") : "") + ScreenRecorder.message
                    color: ScreenRecorder.failed ? Appearance.m3colors.m3error : Appearance.colors.colSubtext
                    font.pixelSize: Appearance.font.pixelSize.small
                    wrapMode: Text.WordWrap
                    Accessible.role: Accessible.StaticText
                }
            }
        }

        SegmentedControl {
            objectName: "recorder-navigation"
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            model: root.tabs
            currentIndex: root.currentTab
            onActivated: index => root.currentTab = index
        }

        StyledFlickable {
            id: page
            objectName: "recorder-options"
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentWidth: width
            contentHeight: optionsColumn.implicitHeight + 16

            ColumnLayout {
                id: optionsColumn
                width: page.width
                spacing: 16

                Repeater {
                    model: root.groups
                    delegate: SettingsSection {
                        id: group
                        required property string modelData
                        property bool expandedDetails: false
                        readonly property var fields: RecordingLayout.fieldsForGroup(ScreenRecorder.fields, modelData)
                        readonly property int compactCount: fields.filter(field => !RecordingLayout.fullWidth(field)).length
                        title: Translation.tr(modelData)
                        icon: ({Files: "folder", Video: "movie", Audio: "volume_up", Capture: "screenshot_region", "Replay & streaming": "replay", "Encoding & color": "memory", Advanced: "tune"})[modelData] || "tune"

                        GridLayout {
                            id: fieldsGrid
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            columns: width >= 480 ? 2 : 1
                            columnSpacing: 20
                            rowSpacing: 16
                            uniformCellWidths: true
                            Repeater {
                                model: group.fields
                                delegate: RecorderField {
                                    required property var modelData
                                    required property int index
                                    visible: group.modelData !== "Capture" || ["mode", "defaultTarget"].includes(modelData.key) || group.expandedDetails
                                    Layout.columnSpan: RecordingLayout.fullWidth(modelData) || (index === group.compactCount - 1 && group.compactCount % 2 === 1) ? fieldsGrid.columns : 1
                                    Layout.alignment: Qt.AlignTop
                                    field: modelData
                                    value: root.draft[modelData.key] ?? modelData.default
                                    onEdited: value => root.put(modelData.key, value)
                                }
                            }
                        }
                        ActionButton {
                            objectName: "recorder-capture-options"
                            visible: group.modelData === "Capture"
                            Layout.maximumWidth: parent.width
                            materialIcon: group.expandedDetails ? "expand_less" : "expand_more"
                            mainText: Translation.tr("Capture options")
                            Accessible.expanded: group.expandedDetails
                            onClicked: group.expandedDetails = !group.expandedDetails
                        }
                        ActionButton {
                            visible: group.modelData === "Capture" && ["replay", "stream"].includes(root.draft.mode)
                            Layout.maximumWidth: parent.width
                            materialIcon: "arrow_forward"
                            mainText: Translation.tr("Replay & streaming")
                            onClicked: root.currentTab = 3
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            visible: group.modelData === "Files"
                            spacing: 8
                            ActionButton {
                                Layout.maximumWidth: parent.width
                                materialIcon: "preview"
                                mainText: Translation.tr("Preview filename")
                                enabled: !ScreenRecorder.busy
                                onClicked: ScreenRecorder.previewName(root.draft)
                            }
                            StyledText {
                                Layout.fillWidth: true
                                visible: text.length > 0
                                text: ScreenRecorder.preview
                                wrapMode: Text.WrapAnywhere
                                font.pixelSize: Appearance.font.pixelSize.smaller
                                color: Appearance.colors.colSubtext
                            }
                        }
                        GridLayout {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            visible: group.modelData === "Audio"
                            columns: width >= 600 ? 2 : 1
                            columnSpacing: 12
                            rowSpacing: 8
                            StyledComboBox {
                                id: source
                                objectName: "recorder-audio-source"
                                Layout.fillWidth: true
                                Layout.minimumWidth: 0
                                model: ScreenRecorder.capabilities.audio.concat(ScreenRecorder.capabilities.applications.map(app => ({id: "app:" + app.id, name: app.name})))
                                textRole: "name"
                                Accessible.name: Translation.tr("Audio source")
                            }
                            ActionButton {
                                objectName: "recorder-add-audio-track"
                                Layout.maximumWidth: parent.width
                                materialIcon: "add"
                                mainText: Translation.tr("Add as separate audio track")
                                enabled: source.currentIndex >= 0
                                onClicked: root.put("audioTracks", [...(root.draft.audioTracks || []), source.model[source.currentIndex].id])
                            }
                        }
                        StyledText {
                            Layout.fillWidth: true
                            visible: group.modelData === "Capture" && group.expandedDetails
                            text: Translation.tr("Capture sources: ") + ScreenRecorder.capabilities.capture.map(item => item.id).join(" · ")
                            wrapMode: Text.WrapAnywhere
                            font.pixelSize: Appearance.font.pixelSize.smaller
                            color: Appearance.colors.colSubtext
                        }
                    }
                }
                EnvironmentPaths {
                    visible: root.currentTab === 3
                    entries: [{name: "GPU Screen Recorder", path: ScreenRecorder.store, exists: ScreenRecorder.preferencesExist}, {name: Translation.tr("Recording state & log"), path: ScreenRecorder.statePath, exists: ScreenRecorder.loaded}]
                }
            }
        }
    }

    component ActionButton: RippleButtonWithIcon {
        id: actionButton
        implicitHeight: Math.max(40, contentItem.implicitHeight + 12)
        Accessible.name: mainText
        mainContentComponent: StyledText {
            text: actionButton.mainText
            color: actionButton.foregroundColor
            wrapMode: Text.WordWrap
            font.pixelSize: Appearance.font.pixelSize.small
        }
    }
}
