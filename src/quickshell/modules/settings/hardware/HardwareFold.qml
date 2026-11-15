pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import qs.services
import qs.modules.shared.primitives.common
import qs.modules.shared.widgets
import ".."

SettingsSection {
    id: root
    property bool expanded: false
    property Component body
    property int count: -1
    showHeader: false
    RippleButtonWithIcon {
        objectName: root.objectName + "-toggle"
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        surfaceVisible: false
        materialIcon: root.expanded ? "expand_less" : "expand_more"
        mainText: root.title + (root.count >= 0 ? " · " + root.count : "")
        Accessible.name: mainText
        Accessible.description: root.expanded ? Translation.tr("Expanded") : Translation.tr("Collapsed")
        onClicked: root.expanded = !root.expanded
        mainContentComponent: HardwareText { text: root.title + (root.count >= 0 ? " · " + root.count : "") }
    }
    Loader {
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        active: root.expanded
        visible: active
        sourceComponent: root.body
    }
}
