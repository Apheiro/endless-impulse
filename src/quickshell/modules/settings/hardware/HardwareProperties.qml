pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import qs.services
import qs.modules.shared
import qs.modules.shared.primitives.common
import qs.modules.shared.widgets

ColumnLayout {
    id: root
    property var values: ({})
    property int limit: 24
    readonly property var keys: Object.keys(values || {})
    Layout.fillWidth: true
    Layout.minimumWidth: 0
    onValuesChanged: limit = 24
    Repeater {
        model: root.keys.slice(0, root.limit)
        delegate: GridLayout {
            id: pair
            required property string modelData
            Layout.fillWidth: true
            columns: 2
            columnSpacing: 12
            HardwareText {
                Layout.preferredWidth: Appearance.font.pixelSize.small * 8
                Layout.fillWidth: false
                Layout.alignment: Qt.AlignTop
                color: Appearance.colors.colSubtext
                text: Translation.tr(pair.modelData)
            }
            HardwareText {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                text: String(root.values[pair.modelData] ?? "") || Translation.tr("Not exposed")
            }
        }
    }
    RippleButtonWithIcon {
        visible: root.keys.length > root.limit
        materialIcon: "expand_more"
        mainText: Translation.tr("Show more") + " · " + (root.keys.length - root.limit)
        onClicked: root.limit += 24
    }
}
