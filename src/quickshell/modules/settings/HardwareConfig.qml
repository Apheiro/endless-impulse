pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Window
import QtQuick.Layouts
import qs.services
import qs.modules.shared
import qs.modules.shared.primitives.common
import qs.modules.shared.primitives.settings
import qs.modules.shared.widgets
import "hardware"

Item {
    id: root
    readonly property real uiScale: Math.max(1, Appearance.font.pixelSize.small / 14)
    readonly property bool wide: width >= 850 * uiScale
    readonly property bool monitoringActive: visible && !!root.Window.window?.visible
    property int tab: 0
    property bool showDetail: false
    readonly property alias inventory: inventory
    readonly property alias inspector: inspector
    readonly property alias ruleEditor: rules
    onMonitoringActiveChanged: Hardware.active = monitoringActive
    Component.onCompleted: Hardware.active = monitoringActive
    Component.onDestruction: Hardware.active = false
    function select(identity) { Hardware.select(identity); showDetail = true; }
    function edit(rule) { rules.edit(rule); tab = 1; }
    function rule() { return rules.rule(); }
    function prepare() { rules.prepare(); tab = 1; }
    function diagnostic(code) {
        const messages = {
            "device-disconnected": Translation.tr("The device disconnected. Refresh and select it again."),
            "invalid-rule-id": Translation.tr("Use 1–48 lowercase letters, digits or hyphens for the draft identifier."),
            "invalid-label": Translation.tr("The description must be at most 120 characters without control characters."),
            "unsupported-subsystem-or-kernel": Translation.tr("This subsystem or kernel selector is unsupported. Select a USB device, hidraw, event or USB serial interface."),
            "exact-usb-ids-required": Translation.tr("Exact four-digit hexadecimal USB vendor and product IDs are required."),
            "unsafe-mode": Translation.tr("Only 0600 or 0660 permission modes are allowed."),
            "invalid-group": Translation.tr("Enter an existing group name without spaces or special characters."),
            "group-not-found": Translation.tr("The selected group does not exist on this host."),
            "rule-action-required": Translation.tr("Choose uaccess, a permission mode or a group."),
            "backup-unavailable": Translation.tr("No previous draft collection is available to restore."),
            "unsafe-draft-path": Translation.tr("Draft storage contains an unsafe path or symbolic link."),
            "backend-timeout": Translation.tr("Hardware reading timed out. Automatic refresh is paused; use Refresh to retry."),
            "tool-unavailable": Translation.tr("An optional host tool is unavailable."),
            "command-failed": Translation.tr("The host tool could not read this device."),
            "command-timeout-or-denied": Translation.tr("The host query timed out or access was denied."),
            "invalid-draft-store": Translation.tr("Draft metadata is invalid. The stored files have been preserved."),
            "backend-read-or-storage-failed": Translation.tr("Reading hardware or writing draft metadata failed. Inspect and retry manually.")
        };
        return messages[code] || Translation.tr("Hardware request could not be completed") + " (" + code + ")";
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: root.wide ? 16 : 8
        spacing: 12
        RowLayout {
            Layout.fillWidth: true
            HardwareText {
                text: Translation.tr("Hardware")
                font.pixelSize: Appearance.font.pixelSize.larger
                font.weight: Font.Medium
            }
            RippleButtonWithIcon {
                objectName: "hardware-refresh"
                mainText: root.wide ? Translation.tr("Refresh") : ""
                materialIcon: "refresh"
                Accessible.name: Translation.tr("Refresh / retry")
                enabled: !Hardware.busy
                onClicked: Hardware.refresh()
            }
        }
        HardwareText {
            color: Appearance.colors.colSubtext
            text: Hardware.projection.componentCount + " " + Translation.tr("components") + " · "
                + Hardware.projection.rawNodeCount + " " + Translation.tr("technical nodes")
                + (Hardware.busy ? " · " + Translation.tr("Reading…") : "")
        }
        SegmentedControl {
            objectName: "hardware-main-tabs"
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            currentIndex: root.tab
            model: [{name: Translation.tr("Devices"), icon: "developer_board"}, {name: Translation.tr("udev rules (drafts)"), icon: "rule"}]
            onActivated: index => root.tab = index
        }
        HardwareText {
            visible: Hardware.error !== "" || Hardware.result !== ""
            text: Hardware.error ? root.diagnostic(Hardware.error) : Translation.tr("Draft collection saved and verified. Host permissions were not changed.")
            color: Hardware.error ? Appearance.colors.colError : Appearance.colors.colOnLayer0
        }
        HardwareText {
            visible: Hardware.monitorStatus === "unavailable" || Hardware.retryRequired || Hardware.snapshot.warnings.length > 0
            text: Hardware.retryRequired ? Translation.tr("Automatic refresh paused after a read error. Use Refresh / retry.")
                : Hardware.snapshot.warnings.length ? Translation.tr("Partial inventory: sysfs remains available; udev properties may be missing.")
                : Translation.tr("Hotplug monitoring unavailable. Use Refresh to update the inventory.")
            color: Appearance.colors.colSubtext
        }
        Item {
            id: panes
            visible: root.tab === 0
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 0
            SettingsCard {
                id: navigation
                objectName: "hardware-navigation-pane"
                visible: root.wide || !root.showDetail
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                width: root.wide ? Math.round((panes.width - 16) * 0.36) : panes.width
                HardwareInventory {
                    id: inventory
                    anchors.fill: parent
                    anchors.margins: 12
                    onChosen: identity => root.select(identity)
                }
            }
            ColumnLayout {
                id: detailPane
                objectName: "hardware-detail-pane"
                visible: root.wide || root.showDetail
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                width: root.wide ? panes.width - navigation.width - 16 : panes.width
                RippleButtonWithIcon {
                    objectName: "hardware-narrow-back"
                    visible: !root.wide
                    materialIcon: "arrow_back"
                    mainText: Translation.tr("Back to devices")
                    onClicked: root.showDetail = false
                }
                HardwareInspector {
                    id: inspector
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumWidth: 0
                    Layout.minimumHeight: 0
                    onPrepareRule: root.prepare()
                    onRevealConnection: identity => { inventory.reveal(identity); if (!root.wide) root.showDetail = false; }
                }
            }
        }
        HardwareRules {
            id: rules
            visible: root.tab === 1
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumWidth: 0
            Layout.minimumHeight: 0
            onReturnToDevice: identity => { root.tab = 0; root.select(identity); }
        }
    }
}
