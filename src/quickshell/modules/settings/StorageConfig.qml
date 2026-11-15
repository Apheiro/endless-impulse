pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Window
import QtQuick.Layouts
import qs.services
import qs.modules.shared
import qs.modules.shared.primitives.common
import qs.modules.shared.primitives.settings
import qs.modules.shared.widgets
import "storage"

SettingsPage {
    id: root
    objectName: "storage-page"
    baseWidth: Math.max(0, width - 32)
    readonly property bool wide: baseWidth >= 720 * Math.max(1, Appearance.font.pixelSize.small / 14)
    readonly property bool monitoringActive: visible && !!root.Window.window?.visible
    readonly property var volume: Storage.selected
    property bool advanced: false
    onMonitoringActiveChanged: Storage.active = monitoringActive
    Component.onCompleted: Storage.active = monitoringActive
    Component.onDestruction: Storage.active = false
    component Label: StyledText {
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        textFormat: Text.PlainText
        wrapMode: Text.Wrap
        color: Appearance.colors.colOnLayer0
    }
    RowLayout {
        Layout.fillWidth: true
        Label { text: Translation.tr("Storage"); font.pixelSize: Appearance.font.pixelSize.larger; font.weight: Font.DemiBold }
        RippleButton {
            objectName: "storage-devices-previous"
            visible: devices.contentWidth > devices.width
            enabled: devices.contentX > 0
            implicitWidth: 32; implicitHeight: 32
            Accessible.name: Translation.tr("Previous devices")
            contentItem: MaterialSymbol { text: "chevron_left"; iconSize: 22; color: Appearance.colors.colOnLayer0 }
            onClicked: devices.contentX = Math.max(0, devices.contentX - devices.width * .8)
        }
        RippleButton {
            objectName: "storage-devices-next"
            visible: devices.contentWidth > devices.width
            enabled: devices.contentX < devices.contentWidth - devices.width
            implicitWidth: 32; implicitHeight: 32
            Accessible.name: Translation.tr("More devices")
            contentItem: MaterialSymbol { text: "chevron_right"; iconSize: 22; color: Appearance.colors.colOnLayer0 }
            onClicked: devices.contentX = Math.min(devices.contentWidth - devices.width, devices.contentX + devices.width * .8)
        }
        RippleButtonWithIcon { objectName: "storage-refresh"; materialIcon: "refresh"; mainText: Translation.tr("Refresh devices"); enabled: !Storage.scanning && !Storage.loading; onClicked: Storage.refresh() }
    }
    StyledFlickable {
        id: devices
        objectName: "storage-volumes"
        Layout.fillWidth: true
        implicitHeight: deviceList.implicitHeight + 8
        contentWidth: deviceList.implicitWidth
        contentHeight: height
        flickableDirection: Flickable.HorizontalFlick
        clip: true
        Behavior on contentX { NumberAnimation { duration: Appearance.animation.scroll.duration; easing.type: Appearance.animation.scroll.type; easing.bezierCurve: Appearance.animation.scroll.bezierCurve } }
        StorageVolumeList { id: deviceList; height: implicitHeight }
    }
    Label {
        visible: Storage.ready && !Storage.loading && !Storage.disks.length && !Storage.volumes.length
        text: Translation.tr("No storage devices are available. Connect a device and refresh.")
        color: Appearance.colors.colSubtext
    }
    Label { visible: Storage.loading; text: Translation.tr("Reading storage devices…"); color: Appearance.colors.colSubtext }
    Label { visible: !!Storage.warning; text: Translation.tr("Physical device information is unavailable. Mounted filesystems are still listed."); color: Appearance.colors.colSubtext }
    Label { objectName: "storage-error"; visible: !!Storage.error && !root.volume?.mounted; text: root.diagnostic(Storage.error); color: Appearance.colors.colPrimary }
    SettingsCard {
        id: analysisCard
        objectName: "storage-detail"
        Layout.fillWidth: true
        implicitHeight: analysis.implicitHeight + 32
        visible: !!root.volume
        ColumnLayout {
            id: analysis
            anchors { left: parent.left; right: parent.right; top: parent.top; margins: 16 }
            spacing: 12
            RowLayout {
                Layout.fillWidth: true
                MaterialSymbol { text: root.volume?.logical ? "cloud" : "hard_drive"; iconSize: 27; color: Appearance.colors.colPrimary }
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    spacing: 2
                    Label { text: Translation.tr(root.volume?.name || ""); font.weight: Font.DemiBold; font.pixelSize: Appearance.font.pixelSize.larger }
                    Label { text: root.volume?.mounted ? root.volume.mount + " · " + root.volume.fs : [root.volume?.transport?.toUpperCase(),root.volume?.media, root.volume?.fs].filter(Boolean).join(" · "); color: Appearance.colors.colSubtext; font.pixelSize: Appearance.font.pixelSize.smaller }
                }
                StyledText { text: Storage.formatBytes(root.volume?.total ?? root.volume?.size); color: Appearance.colors.colOnLayer0; font.pixelSize: Appearance.font.pixelSize.larger }
            }
            Label {
                visible: !root.volume?.mounted
                text: root.volume?.disk ? Translation.tr("Choose a mounted partition below this device to explore its folders. Unmounted partitions cannot be analyzed.") : Translation.tr("Not mounted: this partition cannot be analyzed until it is mounted.")
                color: Appearance.colors.colSubtext
            }
            ColumnLayout {
                visible: !!root.volume?.mounted
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                spacing: 10
                Label {
                    visible: !root.volume?.accessible
                    text: Translation.tr("Filesystem capacity is unavailable. Readable directory allocation can still be shown.")
                    color: Appearance.colors.colSubtext
                }
                StorageAnalysisStatus {
                    objectName: "storage-analysis-status"
                    onWarningsRequested: { root.advanced = true; Qt.callLater(() => root.contentY = Math.max(0, advancedSection.mapToItem(root.contentItem, 0, 0).y - 16)); }
                    Layout.fillWidth: true
                    visible: ["loading", "running", "error", "incomplete", "cancelled"].includes(Storage.analysisState)
                }
                ColumnLayout {
                    objectName: "storage-coverage-warning"
                    visible: Storage.hasWarnings
                    Layout.fillWidth: true
                    spacing: 6
                    RowLayout {
                        Layout.fillWidth: true
                        MaterialSymbol { text: "warning"; iconSize: 22; color: Appearance.colors.colPrimary }
                        Label { text: Translation.tr("Analysis finished with warnings — coverage incomplete"); font.weight: Font.DemiBold }
                        RippleButtonWithIcon {
                            materialIcon: "info"
                            mainText: Translation.tr("Review warnings")
                            onClicked: { root.advanced = true; Qt.callLater(() => root.contentY = Math.max(0, advancedSection.mapToItem(root.contentItem, 0, 0).y - 16)); }
                        }
                    }
                    Label {
                        text: (Storage.summary?.unreadableCount || 0) + " " + Translation.tr("read/coverage issues")
                        color: Appearance.colors.colSubtext
                    }
                    Label {
                        text: Translation.tr("Only observed bytes are shown. Incident counts do not give a number or size of missing files; missing bytes are never assigned to Other folders.")
                        color: Appearance.colors.colSubtext
                        font.pixelSize: Appearance.font.pixelSize.smaller
                    }
                }
                Label {
                    objectName: "storage-changes-info"
                    visible: Storage.hasChanges
                    text: (Storage.summary?.unstableEntries || 0) + " " + Translation.tr("directories changed during analysis; counts may vary.")
                        + (Storage.summary?.coverageUncertain ? " " + Translation.tr("Directory entries changed; some entries may have been missed. Reanalyze for a newer snapshot.") : "")
                    color: Appearance.colors.colSubtext
                    font.pixelSize: Appearance.font.pixelSize.smaller
                }
                Label {
                    objectName: "storage-cache-info"
                    visible: Storage.hasComplete && Storage.fromCache && !Storage.scanning
                    text: Translation.tr("Session snapshot — reused without a new scan")
                    color: Appearance.colors.colSubtext
                    font.pixelSize: Appearance.font.pixelSize.smaller
                }
                StorageUsageBar {
                    id: usage
                    visible: Storage.hasComplete
                    Layout.fillWidth: true
                    onWidthChanged: if (width > 0) Storage.chartWidth = width
                    onFolderSelected: (path, nodeId) => { Storage.highlightedPath = path; Storage.highlightedNodeId = nodeId; Storage.othersOnly = false; }
                    onOthersSelected: Storage.showOthers()
                }
                RowLayout {
                    Layout.fillWidth: true
                    Label {
                        text: Translation.tr("Used") + " " + Storage.formatBytes(root.volume?.used) + " (" + (root.volume?.percent || 0).toFixed(1) + "%)" + (Storage.hasWarnings ? " · " + Translation.tr("Free") + " " + Storage.formatBytes(root.volume?.available) + " · " + Translation.tr("Reserved") + " " + Storage.formatBytes(root.volume?.reserved) : "")
                        color: Appearance.colors.colSubtext
                        font.pixelSize: Appearance.font.pixelSize.smaller
                    }
                    RippleButtonWithIcon {
                        objectName: "storage-reanalyze"
                        visible: !["loading", "running", "error", "incomplete", "cancelled"].includes(Storage.analysisState)
                        materialIcon: Storage.scanning ? "stop" : "refresh"
                        mainText: Storage.scanning ? (Storage.cancelling ? Translation.tr("Cancelling…") : Translation.tr("Cancel")) : Translation.tr("Reanalyze")
                        enabled: Storage.ready && Storage.backend.available && !Storage.cancelling
                        onClicked: Storage.scanning ? Storage.cancel() : Storage.analyze()
                    }
                }
                Label {
                    objectName: "storage-coverage"
                    visible: Storage.hasComplete && (usage.chart.unknown > 0 || usage.chart.excess > 0 || usage.chart.warningDifference > 0)
                    text: usage.chart.excess ? Translation.tr("Counted allocation exceeds filesystem used space by") + " " + Storage.formatBytes(usage.chart.excess) + ". " + Translation.tr("The chart shows directory allocation, not volume capacity.")
                        : Translation.tr("Counted allocation") + " " + Storage.formatBytes(usage.chart.known) + " · " + Translation.tr("Difference from filesystem used space") + " " + Storage.formatBytes(usage.chart.warningDifference || usage.chart.unknown) + ". " + Translation.tr("This difference is not a measured folder, inaccessible-file size or reclaimable space.")
                    color: Appearance.colors.colSubtext
                    font.pixelSize: Appearance.font.pixelSize.smaller
                }
                Label {
                    visible: !!root.volume?.low
                    text: Translation.tr("Less than 10% available to your user.")
                    color: Appearance.colors.colPrimary
                }
                Label {
                    objectName: "storage-exclusions-info"
                    visible: Storage.hasComplete && !!Storage.summary?.excludedCount
                    text: Translation.tr("Other mountpoints and protected paths were intentionally excluded.") + " (" + (Storage.summary?.excludedCount || 0) + ")"
                    color: Appearance.colors.colSubtext
                    font.pixelSize: Appearance.font.pixelSize.smaller
                }
                Label {
                    visible: !Storage.backend.available
                    text: Translation.tr("The native Storage engine is missing. Rebuild or reinstall the Storage runtime; no fallback scanner is used.")
                }
                StorageFolderBrowser { id: folders; objectName: "storage-folders"; Layout.fillWidth: true; visible: Storage.hasComplete; chartColors: usage }
                Label { visible: !Storage.view && Storage.analysisState === "idle" && Storage.backend.available; text: Translation.tr("No folder snapshot yet. Reanalyze to retry."); color: Appearance.colors.colSubtext }
            }
        }
    }
    RippleButtonWithIcon {
        objectName: "storage-advanced-toggle"
        materialIcon: root.advanced ? "expand_less" : "tune"
        mainText: Translation.tr("Advanced & details")
        onClicked: root.advanced = !root.advanced
    }
    SettingsSection {
        id: advancedSection
        objectName: "storage-advanced"
        visible: root.advanced
        title: Translation.tr("Analysis scope & diagnostics")
        icon: "tune"
        Label { text: (root.volume?.source || "") + " · " + (root.volume?.mounts || []).join(" · "); color: Appearance.colors.colSubtext }
        Label { text: Translation.tr("Allocated bytes from the native engine can differ from filesystem usage: permissions, excluded mounts, metadata, snapshots, compression and shared blocks."); color: Appearance.colors.colSubtext }
        Label { visible: !!root.volume?.accessible; text: Translation.tr("Exact bytes") + ": " + Storage.exact(root.volume?.total) + " · " + Translation.tr("Used") + " " + Storage.exact(root.volume?.used) + " · " + Translation.tr("Free") + " " + Storage.exact(root.volume?.available) + " · " + Translation.tr("Reserved") + " " + Storage.exact(root.volume?.reserved) }
        Repeater {
            model: root.volume?.mounted ? (root.volume.mounts || []).filter(path => path !== root.volume.mount) : []
            delegate: RippleButtonWithIcon {
                id: mountAction
                required property string modelData
                mainContentComponent: Component {
                    StyledText { text: mountAction.mainText; textFormat: Text.PlainText; elide: Text.ElideMiddle; color: mountAction.foregroundColor }
                }
                mainText: Translation.tr("Analyze mounted location") + ": " + modelData
                materialIcon: "folder_open"
                Layout.maximumWidth: parent.width
                enabled: !Storage.scanning
                onClicked: Storage.analyze(modelData)
            }
        }
        StyledComboBox {
            objectName: "storage-workers"
            Layout.fillWidth: true
            model: [Translation.tr("Workers: engine default"), Translation.tr("1 worker — HDD / limited I/O"), Translation.tr("2 workers"), Translation.tr("3 workers"), Translation.tr("4 workers")]
            currentIndex: Storage.workers
            onActivated: index => Storage.workers = index
            enabled: !Storage.scanning
        }
        Label {
            text: Translation.tr("Parallelism applies to the next scan. Use 1 for HDD; no automatic device detection.") + " " + Translation.tr("Snapshots stay in memory only while Settings is running; closing it loses the cache.")
            color: Appearance.colors.colSubtext
        }
        MaterialTextField { id: customPath; objectName: "storage-scan-path"; Layout.fillWidth: true; text: root.volume?.mount || ""; placeholderText: Translation.tr("Custom directory within this volume") }
        RippleButtonWithIcon { objectName: "storage-custom-analyze"; mainText: Translation.tr("Analyze this directory"); materialIcon: "folder_open"; enabled: Storage.ready && Storage.backend.available && !Storage.scanning && !!root.volume?.mounted; onClicked: Storage.analyze(customPath.text) }
        Repeater {
            model: Storage.view?.excluded || []
            delegate: Label { required property var modelData; text: modelData.path + " · " + modelData.reason; color: Appearance.colors.colSubtext }
        }
        Label {
            visible: Storage.hasComplete
            text: Translation.tr("Read/coverage issues") + ": " + (Storage.view?.unreadableCount || 0) + " · " + Translation.tr("Directories changed during analysis") + ": " + (Storage.view?.unstableEntries || 0) + " · " + Translation.tr("Excluded entries") + ": " + (Storage.view?.excludedEntries || 0)
            color: Appearance.colors.colSubtext
        }
        Repeater {
            model: Storage.view?.issues || []
            delegate: Label {
                required property var modelData
                text: modelData.category + " · " + modelData.code + (modelData.errno !== null ? " · errno " + modelData.errno : "")
                color: Appearance.colors.colSubtext
            }
        }
        Label {
            objectName: "storage-issue-histogram"
            visible: Storage.hasComplete
            text: Translation.tr("Incident codes (no paths)") + ": " + JSON.stringify(Storage.summary?.issueCodes || {})
                + " · " + Translation.tr("Execution") + ": " + JSON.stringify(Storage.summary?.execution || {})
            color: Appearance.colors.colSubtext
        }
        Label {
            visible: !!Storage.diagnostic
            text: Translation.tr("Diagnostic") + ": " + JSON.stringify(Storage.diagnostic)
            color: Appearance.colors.colSubtext
        }
    }
    function diagnostic(code) {
        const labels = {
            "volume-disconnected": "This volume is no longer mounted. Refresh the volume list.",
            "outside-volume": "Choose a directory inside this volume. Nested mounts belong to a different filesystem.",
            "symlink-path": "Symbolic links cannot be used as analysis paths. Enter the original directory.",
            "protected-path": "This directory is protected and excluded from analysis.",
            "backend-timeout": "The filesystem took too long to respond. Retry manually when it is available.",
            "cancelled": "Analysis cancelled. The worker was closed because the filesystem did not respond.",
            "backend-stopped": "The storage worker stopped. Retry to reconnect.",
            "PermissionError": "This directory cannot be read with your current permissions.",
            "FileNotFoundError": "The directory no longer exists. Refresh and choose another location.",
            "invalid-path": "Enter an absolute directory path inside the selected volume."
        };
        return Translation.tr(labels[code] || "Storage could not finish the request. Refresh or retry manually.");
    }
}
