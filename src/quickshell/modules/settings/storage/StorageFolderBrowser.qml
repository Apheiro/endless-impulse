pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import qs.services
import qs.modules.shared
import qs.modules.shared.primitives.common
import qs.modules.shared.widgets
import "StorageMath.js" as Accounting

ColumnLayout {
    id: root
    Layout.minimumWidth: 0
    spacing: 6
    property var chartColors
    readonly property var breadcrumbs: Storage.view?.breadcrumbs || []
    Flow {
        Layout.fillWidth: true
        spacing: 3
        Repeater {
            model: root.breadcrumbs
            delegate: RippleButton {
                required property var modelData
                required property int index
                objectName: "storage-breadcrumb-" + index
                buttonText: modelData.name
                implicitWidth: Math.min(implicitContentWidth + 22, root.width)
                implicitHeight: 32
                surfaceVisible: false
                contentItem: StyledText { text: parent.modelData.name; textFormat: Text.PlainText; elide: Text.ElideMiddle; color: Appearance.colors.colPrimary }
                onClicked: Storage.browse(modelData.path, 0, false, modelData.nodeId)
            }
        }
    }
    RowLayout {
        Layout.fillWidth: true
        MaterialTextField {
            id: search
            objectName: "storage-filter"
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            placeholderText: Translation.tr("Filter folders")
            text: Storage.query
            onTextEdited: Storage.filterFolders(text)
        }
        RippleButtonWithIcon {
            objectName: "storage-sort"
            materialIcon: "sort"
            mainText: Storage.order === "size" ? Translation.tr("Size") : Translation.tr("Name")
            onClicked: { Storage.order = Storage.order === "size" ? "name" : "size"; Storage.browse(Storage.view.path, 0, true); }
        }
    }
    RowLayout {
        visible: Storage.othersOnly
        Layout.fillWidth: true
        StyledText { Layout.fillWidth: true; text: Translation.tr("Other folders — only the smaller children"); color: Appearance.colors.colSubtext; wrapMode: Text.Wrap }
        RippleButtonWithIcon { mainText: Translation.tr("Show all"); materialIcon: "close"; onClicked: Storage.browse(Storage.view.path) }
    }
    RowLayout {
        visible: !!Storage.highlightedPath
        Layout.fillWidth: true
        StyledText { Layout.fillWidth: true; Layout.minimumWidth: 0; text: Storage.highlightedPath; textFormat: Text.PlainText; elide: Text.ElideMiddle; color: Appearance.colors.colPrimary }
        RippleButtonWithIcon { objectName: "storage-enter-highlighted"; materialIcon: "arrow_forward"; mainText: Translation.tr("Open folder"); onClicked: Storage.browse(Storage.highlightedPath, 0, false, Storage.highlightedNodeId) }
    }
    Repeater {
        model: Storage.view?.rows || []
        delegate: RippleButton {
            id: row
            required property var modelData
            required property int index
            objectName: "storage-folder-" + index
            Layout.fillWidth: true
            implicitHeight: 46 * Math.max(1, Appearance.font.pixelSize.small / 14)
            enabled: !modelData.excluded
            Accessible.description: (modelData.unreadableCount || 0) + " " + Translation.tr("Read/coverage issues") + " · " + (modelData.unstableEntries || 0) + " " + Translation.tr("Directories changed during analysis") + (modelData.excluded ? " · " + Translation.tr("Intentionally excluded") : "")
            toggled: Storage.highlightedNodeId === modelData.nodeId
            onClicked: Storage.browse(modelData.path, 0, false, modelData.nodeId)
            contentItem: RowLayout {
                spacing: 10
                MaterialSymbol { text: "folder"; iconSize: 21; color: row.toggled ? Appearance.m3colors.m3onPrimary : root.chartColors.segmentColor(Object.assign({kind:"folder"}, row.modelData)) }
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    spacing: 5
                    StyledText {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        text: row.modelData.name
                        textFormat: Text.PlainText
                        elide: Text.ElideMiddle
                        color: row.toggled ? Appearance.m3colors.m3onPrimary : Appearance.colors.colOnLayer0
                    }
                    Rectangle {
                        id: track
                        objectName: "storage-folder-track-" + row.index
                        Layout.fillWidth: true
                        implicitHeight: 3
                        clip: true
                        color: root.chartColors.progressTrackColor()
                        Rectangle {
                            id: fill
                            objectName: "storage-folder-fill-" + row.index
                            height: parent.height
                            width: track.width * Accounting.boundedRatio(row.modelData.bytes, Storage.view?.bytes || 0)
                            color: root.chartColors.progressFillColor(Object.assign({kind:"folder"}, row.modelData), track.color)
                        }
                        Rectangle {
                            objectName: "storage-folder-tiny-" + row.index
                            visible: fill.width > 0 && fill.width < 2
                            width: Math.min(1, track.width)
                            height: track.height
                            color: fill.color
                            Accessible.name: Translation.tr("Non-zero allocation below two pixels; use the exact size label.")
                        }
                    }
                }
                StyledText { text: (row.modelData.partial ? "≈ " : "") + Storage.formatBytes(row.modelData.bytes); color: row.toggled ? Appearance.m3colors.m3onPrimary : Appearance.colors.colOnLayer0 }
                MaterialSymbol { visible: (row.modelData.unreadableCount || 0) > 0 || (row.modelData.unstableEntries || 0) > 0 || !!row.modelData.excluded; text: (row.modelData.unreadableCount || 0) > 0 ? "warning" : row.modelData.excluded ? "block" : "info"; iconSize: 18; color: row.toggled ? Appearance.m3colors.m3onPrimary : Appearance.colors.colPrimary }
                MaterialSymbol { text: "chevron_right"; iconSize: 20; color: row.toggled ? Appearance.m3colors.m3onPrimary : Appearance.colors.colSubtext }
            }
        }
    }
    StyledText {
        Layout.fillWidth: true
        visible: !!Storage.view
        text: Translation.tr("Direct entries") + ": " + (Storage.view?.files || 0) + " · " + Storage.formatBytes(Storage.view?.fileBytes || 0)
        color: Appearance.colors.colSubtext
        font.pixelSize: Appearance.font.pixelSize.smaller
        wrapMode: Text.Wrap
    }
    StyledText { visible: !!Storage.view && !Storage.view.count; text: Translation.tr("No subfolders match this view."); color: Appearance.colors.colSubtext }
    RowLayout {
        visible: !!Storage.view && Storage.view.count > Storage.view.pageSize
        Layout.fillWidth: true
        RippleButtonWithIcon { objectName: "storage-previous"; materialIcon: "chevron_left"; mainText: Translation.tr("Previous"); enabled: !!Storage.view?.offset; onClicked: Storage.browse(Storage.view.path, Storage.view.offset - Storage.view.pageSize, true) }
        StyledText { Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; text: ((Storage.view?.offset || 0) + 1) + "–" + Math.min((Storage.view?.offset || 0) + (Storage.view?.pageSize || 60), Storage.view?.count || 0) + " / " + (Storage.view?.count || 0); color: Appearance.colors.colSubtext }
        RippleButtonWithIcon { objectName: "storage-next"; materialIcon: "chevron_right"; mainText: Translation.tr("Next"); enabled: !!Storage.view?.more; onClicked: Storage.browse(Storage.view.path, Storage.view.nextOffset, true) }
    }
}
