pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import qs.services
import qs.modules.shared
import qs.modules.shared.primitives.common
import qs.modules.shared.primitives.settings

RowLayout {
    id: root
    readonly property real uiScale: Math.max(1, Appearance.font.pixelSize.small / 14)
    Layout.minimumWidth: 0
    spacing: 10
    component TextLabel: StyledText {
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        textFormat: Text.PlainText
        wrapMode: Text.Wrap
        color: Appearance.colors.colOnLayer0
    }
    component VolumeRow: RippleButton {
        id: row
        required property var volume
        Layout.fillWidth: true
        toggled: Storage.selectedId === volume.id
        implicitHeight: content.implicitHeight + 16
        objectName: "storage-volume-" + volume.id
        onClicked: Storage.select(volume.id)
        contentItem: TextLabel {
            id: content
            text: (row.volume.name?.startsWith("Partition ") ? Translation.tr("Partition") + " " + row.volume.name.slice(10) : Translation.tr(row.volume.name || "Volume")) + " · " + (row.volume.mounted ? row.volume.mount : Translation.tr("Not mounted"))
            color: row.toggled ? Appearance.m3colors.m3onPrimary : Appearance.colors.colOnLayer0
            maximumLineCount: 1
            elide: Text.ElideMiddle
            font.pixelSize: Appearance.font.pixelSize.smaller
        }

    }
    Repeater {
        model: Storage.disks
        delegate: SettingsCard {
            id: diskCard
            required property var modelData
            objectName: "storage-disk-" + modelData.id
            Layout.preferredWidth: 240 * root.uiScale
            Layout.minimumWidth: 220 * root.uiScale
            Layout.maximumWidth: 260 * root.uiScale
            Layout.alignment: Qt.AlignTop
            implicitHeight: contents.implicitHeight + 20
            emphasized: Storage.selectedId === modelData.id
            ColumnLayout {
                id: contents
                anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10 }
                spacing: 5
                RippleButton {
                    Layout.fillWidth: true
                    implicitHeight: header.implicitHeight + 8
                    surfaceVisible: false
                    onClicked: Storage.select(diskCard.modelData.id)
                    contentItem: RowLayout {
                        id: header
                        MaterialSymbol { text: diskCard.modelData.removable || diskCard.modelData.transport === "usb" ? "usb" : "hard_drive"; iconSize: 22; color: Appearance.colors.colPrimary }
                        ColumnLayout {
                            Layout.fillWidth: true
                            TextLabel { text: diskCard.modelData.name; font.weight: Font.DemiBold; maximumLineCount: 2; elide: Text.ElideRight }
                            TextLabel {
                                text: Storage.formatBytes(diskCard.modelData.size) + " · " + [diskCard.modelData.transport.toUpperCase(), diskCard.modelData.media].filter(Boolean).join(" / ")
                                color: Appearance.colors.colSubtext
                                font.pixelSize: Appearance.font.pixelSize.smaller
                            }
                        }
                    }
                }
                Repeater {
                    model: diskCard.modelData.volumeIds
                    delegate: VolumeRow {
                        id: partitionRow
                        required property var modelData
                        volume: Storage.volumes.find(v => v.id === partitionRow.modelData) || ({})
                    }
                }
            }
        }
    }
    SettingsCard {
        visible: Storage.volumes.some(v => v.logical)
        Layout.preferredWidth: 230 * root.uiScale
        Layout.minimumWidth: 210 * root.uiScale
        Layout.alignment: Qt.AlignTop
        implicitHeight: logicalContents.implicitHeight + 20
        ColumnLayout {
            id: logicalContents
            anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10 }
            spacing: 5
            TextLabel { text: Translation.tr("Logical & remote volumes"); color: Appearance.colors.colSubtext; font.pixelSize: Appearance.font.pixelSize.smaller }
            Repeater {
                model: Storage.volumes.filter(v => v.logical)
                delegate: VolumeRow { id: logicalRow; required property var modelData; volume: logicalRow.modelData }
            }
        }
    }
}
