pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import qs.services
import qs.modules.shared
import qs.modules.shared.primitives.common
import qs.modules.shared.widgets

ColumnLayout {
    id: root
    signal warningsRequested()
    readonly property bool busy: ["loading", "running"].includes(Storage.analysisState)
    Layout.minimumWidth: 0
    spacing: 10
    RowLayout {
        Layout.fillWidth: true
        MaterialSymbol {
            text: root.busy ? "data_usage" : Storage.analysisState === "cancelled" ? "stop_circle" : "error_outline"
            iconSize: 28
            color: Appearance.colors.colPrimary
        }
        StyledText {
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            text: root.busy ? Translation.tr("Analyzing storage…") : Storage.analysisState === "cancelled" ? Translation.tr("Analysis cancelled") : Translation.tr("Analysis incomplete")
            font.weight: Font.DemiBold
            color: Appearance.colors.colOnLayer0
            Accessible.role: Accessible.StatusBar
        }
        RippleButtonWithIcon {
            objectName: "storage-status-action"
            materialIcon: root.busy ? "stop" : "refresh"
            mainText: root.busy ? (Storage.cancelling ? Translation.tr("Cancelling…") : Translation.tr("Cancel")) : Translation.tr("Retry analysis")
            enabled: !Storage.cancelling
            onClicked: {
                if (root.busy) Storage.cancel();
                else Storage.retry();
            }
        }
    }
    StyledIndeterminateProgressBar {
        objectName: "storage-indeterminate"
        Layout.fillWidth: true
        visible: root.busy
        palette.highlight: Appearance.colors.colPrimary
        palette.midlight: Appearance.colors.colSecondaryContainer
        // Visual timing belongs to the native themed control; no invented %.
    }
    StyledText {
        objectName: "storage-progress"
        Layout.fillWidth: true
        wrapMode: Text.Wrap
        color: Appearance.colors.colSubtext
        text: root.busy ? Storage.progress.entries + " " + Translation.tr("entries") + " · " + (Storage.progress.directories || 0) + " " + Translation.tr("directories")
            + " · " + Storage.formatBytes(Storage.progress.bytes) + " · " + Storage.progress.elapsed + " s"
            : root.message(Storage.scanStatus)
    }
    StyledText {
        Layout.fillWidth: true
        wrapMode: Text.Wrap
        color: Appearance.colors.colSubtext
        text: Storage.hasComplete ? Translation.tr("Previous finished result — any coverage warnings still apply.")
            : Translation.tr("The folder chart and browser appear after the native scan finishes. Interrupted scans are never published.")
    }
    RippleButtonWithIcon {
        visible: !root.busy && !!Storage.diagnostic
        materialIcon: "info"
        mainText: Translation.tr("Review warnings")
        onClicked: root.warningsRequested()
    }
    function message(code) {
        const messages = {
            "native-engine-upgrade-required": "The native Storage engine needs rebuilding to classify coverage and changes correctly. Rebuild it and refresh devices.",
            "native-engine-required": "The native Storage engine is missing. Rebuild or reinstall the Storage runtime; no fallback scanner is used.",
            "native-engine-stopped": "The native Storage engine stopped. Retry to reconnect; no interrupted result was published.",
            "native-engine-unresponsive": "The native Storage engine did not answer. Retry manually.",
            "worker-unresponsive": "The storage worker stopped responding. Retry to reconnect.",
            "cancelled": "The analysis was cancelled. No incomplete result was published.",
            "invalid-completion": "The worker returned an unverified result. No result was published.",
            "root_open_failed": "The selected directory could not be opened. Check its existence and your read permissions.",
            "root_read_failed": "The selected directory could not be listed with your current permissions.",
            "mounts_changed": "Mounts changed during analysis. Retry after the volume is stable.",
            "root_changed": "The selected directory changed during analysis. Retry manually.",
            "volume-disconnected": "This volume is no longer mounted. Refresh the volume list.",
            "mount_identity_unavailable": "The kernel could not verify the mount identity. No result was published.",
            "response_too_large": "These directory names exceed the IPC page limit. The native snapshot still retains its detail.",
            "outside-volume": "Choose a directory inside this volume. Nested mounts belong to a different filesystem.",
            "symlink-path": "Symbolic links cannot be used as analysis paths. Enter the original directory.",
            "protected-path": "This directory is protected and excluded from analysis."
        };
        return Translation.tr(messages[code] || "Storage could not finish the request. Refresh or retry manually.");
    }
}
