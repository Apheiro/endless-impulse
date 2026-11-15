pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import qs.services
import qs.modules.shared
import qs.modules.shared.primitives.common
import qs.modules.shared.widgets
import ".."

StyledFlickable {
    id: root
    objectName: "hardware-inspector"
    property var entity: Hardware.selectedEntity
    property var node: Hardware.selectedNode
    property var detail: Hardware.detail
    property int interfaceLimit: 12
    property string componentId: entity?.id || ""
    readonly property var interfaces: entity?.category === "CPU"
        ? entity.memberIds.map(id => Hardware.nodeIndex[id]).filter(n => !!n) : Hardware.interfaces(entity?.id || "")
    readonly property var driverNode: {
        let current = node;
        while (current && !current.driver) current = Hardware.nodeIndex[current.parent];
        return current || null;
    }
    signal prepareRule()
    signal revealConnection(string identity)
    onComponentIdChanged: { interfaceLimit = 12; connection.expanded = false; driver.expanded = false; access.expanded = false; technical.expanded = false; }
    Connections { target: Hardware; function onSelectionRequested() { root.contentY = 0; } }
    contentHeight: content.implicitHeight + 24
    clip: true
    ColumnLayout {
        id: content
        width: Math.max(0, root.width - 12)
        spacing: 12
        SettingsSection {
            visible: !Hardware.selectedId
            title: Translation.tr("Your hardware at a glance")
            icon: "developer_board"
            HardwareText {
                font.pixelSize: Appearance.font.pixelSize.larger
                text: Hardware.projection.componentCount + " " + Translation.tr("components")
            }
            HardwareText { text: Translation.tr("Choose a category, then a component. Its connections, interfaces, driver and access permissions appear here.") }
            HardwareProperties {
                values: ({"Kernel": Hardware.snapshot.kernel?.release || "", "Architecture": Hardware.snapshot.kernel?.architecture || "", "Technical nodes": Hardware.projection.rawNodeCount})
            }
            HardwareText { color: Appearance.colors.colSubtext; text: Translation.tr("Components group related interfaces. The technical node count includes kernel directories and virtual devices; it is not a count of physical devices.") }
        }
        SettingsSection {
            visible: !!Hardware.selectedId
            title: root.entity?.name || root.node?.name || Translation.tr("Device disconnected")
            icon: "developer_board"
            HardwareText { text: (Translation.tr(root.entity?.category || root.node?.category || "")) + " · " + (root.entity?.bus || root.node?.subsystem || "") }
            HardwareText { color: Appearance.colors.colSubtext; maximumLineCount: 2; elide: Text.ElideMiddle; text: root.entity?.breadcrumb || root.node?.id || Hardware.selectedId }
            HardwareText {
                visible: !root.node
                color: Appearance.colors.colError
                text: Translation.tr("This device is no longer present. Refresh or choose another component; the previous selection is preserved for context.")
            }
            HardwareText { visible: Hardware.busy && !root.detail; text: Translation.tr("Reading device details…") }
            HardwareText {
                visible: !!root.entity && root.entity.id !== Hardware.selectedId
                text: Translation.tr("Selected interface") + ": " + (root.node?.kernel || "")
            }
            GridLayout {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                columns: root.width >= 620 ? 2 : 1
                columnSpacing: 18
                HardwareProperties {
                    values: root.node ? {"Bus": root.entity?.bus || root.node.subsystem,
                        "Vendor / product": [root.entity?.vendor || root.node.vendor, root.entity?.product || root.node.product].filter(v => !!v).join(" : "),
                        "Interfaces": root.entity?.interfaceCount ?? 0} : ({})
                }
                HardwareProperties {
                    values: root.node ? {"Driver": root.detail?.driver || root.node.driver,
                        "Module": root.detail?.module,
                        "Binding": root.detail ? Translation.tr(root.detail.binding === "bound" ? "Driver bound" : "No driver bound / not applicable") : Translation.tr("Reading…")} : ({})
                }
            }
            HardwareProperties {
                visible: root.entity?.category === "CPU"
                values: root.entity?.category === "CPU" ? {"Cores": root.entity.coreCount, "Logical CPUs": root.entity.logicalCpuCount} : ({})
            }
            Flow {
                Layout.fillWidth: true
                spacing: 8
                RippleButtonWithIcon {
                    objectName: "hardware-physical-back"
                    visible: !!root.entity && root.entity.id !== Hardware.selectedId
                    mainText: Translation.tr("Back to component")
                    materialIcon: "arrow_back"
                    onClicked: Hardware.select(root.entity.id)
                }
                RippleButtonWithIcon {
                    visible: !!root.entity
                    mainText: Translation.tr("Show connection")
                    materialIcon: "account_tree"
                    onClicked: root.revealConnection(root.entity.id)
                }
            }
        }
        HardwareFold {
            id: connection
            objectName: "hardware-connections"
            visible: !!root.node
            title: Translation.tr("Connection & interfaces")
            count: root.interfaces.length
            body: ColumnLayout {
                spacing: 8
                HardwareProperties { values: ({"Connection": root.entity?.breadcrumb || root.node?.parent || "", "Subsystem": root.node?.subsystem || ""}) }
                RippleButtonWithIcon {
                    visible: !!Hardware.entityIndex[root.entity?.parent || ""]
                    mainText: Translation.tr("Parent component")
                    materialIcon: "arrow_upward"
                    onClicked: Hardware.select(root.entity.parent)
                }
                Repeater {
                    model: root.interfaces.slice(0, root.interfaceLimit)
                    delegate: RippleButtonWithIcon {
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        mainText: modelData.kernel + " · " + modelData.subsystem + (modelData.driver ? " · " + modelData.driver : "")
                        mainContentComponent: HardwareText { text: modelData.kernel + " · " + modelData.subsystem + (modelData.driver ? " · " + modelData.driver : ""); maximumLineCount: 2; elide: Text.ElideRight }
                        materialIcon: "settings_input_component"
                        toggled: modelData.id === Hardware.selectedId
                        onClicked: Hardware.select(modelData.id)
                    }
                }
                RippleButtonWithIcon {
                    visible: root.interfaces.length > root.interfaceLimit
                    mainText: Translation.tr("Show more interfaces") + " · " + root.interfaces.length
                    materialIcon: "expand_more"
                    onClicked: root.interfaceLimit += 12
                }
                HardwareText { visible: !root.interfaces.length; text: Translation.tr("No interfaces exposed for this component.") }
            }
        }
        HardwareFold {
            id: driver
            objectName: "hardware-driver"
            visible: !!root.node
            title: Translation.tr("Driver & kernel")
            body: ColumnLayout {
                spacing: 10
                HardwareProperties { values: root.detail ? {"Binding": Translation.tr(root.detail.binding === "bound" ? "Driver bound" : "No driver bound / not applicable"), "Driver": root.detail.driver, "Module": root.detail.module, "Module state": root.detail.moduleState, "Driver path": root.detail.driverPath} : ({}) }
                RippleButtonWithIcon {
                    visible: !!root.driverNode && root.driverNode.id !== Hardware.selectedId
                    mainText: Translation.tr("Inspect driver on parent") + " · " + (root.driverNode?.kernel || "")
                    materialIcon: "arrow_upward"
                    onClicked: Hardware.select(root.driverNode.id)
                }
                HardwareText { text: Translation.tr("Read-only. No binding, module loading, reset or parameter writes. An unbound interface is not necessarily a fault.") }
                HardwareText { text: Translation.tr("Module parameters"); font.weight: Font.Medium }
                HardwareProperties { values: root.detail?.parameters || ({}) }
                HardwareText { visible: !Object.keys(root.detail?.parameters || {}).length; text: Translation.tr("No readable module parameters exposed. Select a parent or driver-bound interface if appropriate.") }
            }
        }
        HardwareFold {
            id: access
            objectName: "hardware-access"
            visible: !!root.node
            title: Translation.tr("Access & permissions")
            count: root.detail?.nodes?.length || 0
            body: ColumnLayout {
                spacing: 10
                Repeater {
                    model: root.detail?.nodes || []
                    delegate: ColumnLayout {
                        id: permissions
                        required property var modelData
                        Layout.fillWidth: true
                        HardwareProperties { values: {"Device node": permissions.modelData.path, "Mode": permissions.modelData.mode, "Owner / group": permissions.modelData.owner + " : " + permissions.modelData.group} }
                        HardwareText { text: "ACL\n" + (permissions.modelData.acl || Translation.tr("Not exposed")) }
                    }
                }
                HardwareText { visible: !root.detail?.nodes?.length; text: Translation.tr("No device node on this selection. Choose an interface to inspect its permissions or prepare an access draft.") }
                RippleButtonWithIcon {
                    objectName: "hardware-prepare-rule"
                    enabled: !Hardware.busy && !!root.detail?.ruleSupported
                    mainText: Translation.tr("Prepare access draft")
                    materialIcon: "edit"
                    onClicked: root.prepareRule()
                }
                HardwareText { text: Translation.tr("Draft only, not installed. Host permissions remain unchanged.") }
            }
        }
        HardwareFold {
            id: technical
            objectName: "hardware-technical"
            visible: !!root.node
            title: Translation.tr("Advanced: technical properties")
            body: ColumnLayout {
                spacing: 10
                HardwareText { text: Translation.tr("Serials and unique IDs are hidden. Values are only shown when exposed by the kernel or udev.") }
                HardwareProperties { values: root.detail ? {"Sysfs": root.detail.sysfs, "Parent": root.detail.parent} : ({}) }
                HardwareProperties { values: root.detail?.attributes || ({}) }
                HardwareText { text: Translation.tr("Firmware") }
                HardwareProperties { values: root.detail?.firmware || ({}) }
                HardwareText { text: Translation.tr("udev properties") }
                HardwareProperties { values: root.detail?.properties || ({}) }
            }
        }
        HardwareText { visible: !!root.detail?.diagnostics?.length; text: (root.detail?.diagnostics || []).join(" · "); color: Appearance.colors.colSubtext }
    }
}
