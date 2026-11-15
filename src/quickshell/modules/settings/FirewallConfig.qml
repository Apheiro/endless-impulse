pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import qs.services
import qs.modules.shared
import qs.modules.shared.primitives.common
import qs.modules.shared.primitives.settings

Item {
    id: root

    readonly property string connectionText: {
        if (control.refreshing && !control.lastValidRead)
            return Translation.tr("Connecting to Firewalld");
        switch (stateData.state) {
        case "connected":
            return Translation.tr("Connected to Firewalld");
        case "connecting":
            return Translation.tr("Connecting to Firewalld");
        case "not-installed":
            return Translation.tr("Firewalld client not installed");
        case "unavailable":
            return Translation.tr("Firewalld stopped or unavailable");
        case "timeout":
            return Translation.tr("Firewalld request timed out");
        case "agent-unavailable":
            return Translation.tr("Session Polkit agent unavailable");
        case "authorization-unavailable":
            return Translation.tr("Firewall authorization unavailable");
        case "access-denied":
            return Translation.tr("Access denied by Firewalld");
        default:
            return Translation.tr("Firewalld communication error");
        }
    }
    readonly property var control: FirewalldControl
    readonly property var stateData: control.snapshot
    property string page: "home"
    property var pageHistory: []
    property var recordedContext: ({page:"home", scope:"runtime", zoneName:"", section:"", resourceKind:"service", resourceName:""})
    property bool returning: false
    property string scope: "runtime"
    property string zoneName: ""
    property string section: ""
    property bool advancedOpen: false
    property string query: ""
    property var pending: null
    property string assignmentInterface: ""
    readonly property var assignment: connections.find(connection => connection.interface === assignmentInterface) ?? null
    property string resourceKind: "service"
    property string resourceName: ""
    readonly property var zones: stateData.scopes?.[scope]?.zones ?? []
    readonly property var selectedZone: zones.find(zone => zone.name === zoneName) ?? null
    readonly property var fields: selectedZone?.fields ?? ({})
    readonly property var policies: stateData.scopes?.[scope]?.policies ?? []
    readonly property var connections: stateData.complete ? (stateData.connections ?? []) : []
    readonly property var primaryConnection: connections.find(connection => connection.primary) ?? null
    readonly property var catalog: stateData.catalogs?.[scope] ?? ({services: stateData.services ?? []})
    readonly property bool zonePage: ["zone", "section", "zone-details"].includes(page)
    readonly property var commonSections: [
        {title:"Services", field:"services", icon:"apps", detail:"Allow predefined services in this zone."},
        {title:"Ports", field:"ports", icon:"swap_horiz", detail:"Allow incoming TCP or UDP ports."}
    ]
    readonly property var sections: [
        {title: "Protocols", field: "protocols", action: "protocol", hint: "Protocol name or number (0–255)"},
        {title: "Source ports", field: "source-ports", action: "source-port", hint: "Port or range with /tcp or /udp"},
        {title: "Masquerading", field: "masquerade", action: "masquerade"},
        {title: "Port forwarding", field: "forward-ports", action: ""},
        {title: "ICMP filter", field: "icmp-blocks", action: "icmp-block", hint: "ICMP type from the host catalog"},
        {title: "Rich rules", field: "rich rules", action: "rich-rule", hint: "One complete Firewalld rich rule"},
        {title: "Interfaces", field: "interfaces", action: ""},
        {title: "Sources", field: "sources", action: "source", hint: "IP address, network or ipset:name"}
    ]
    readonly property var sectionData: commonSections.concat(sections).find(entry => entry.field === section) ?? ({})
    readonly property var definition: control.definitionContext?.kind === resourceKind
                                      && control.definitionContext?.name === resourceName
                                      && control.definitionContext?.scope === scope ? control.definition : null
    readonly property bool definitionEditable: scope === "permanent" && !!definition
        && (resourceKind === "service" || (definition.fields.type === "hash:ip"
            && !String(definition.fields.options || "").includes("timeout=")
            && !String(definition.fields.options || "").split(/\s+/).includes("family=inet6")))
    readonly property var zoneMetadata: control.definitionContext?.kind === "zone"
                                       && control.definitionContext?.name === zoneName
                                       && control.definitionContext?.scope === scope ? control.definition : null
    readonly property bool portValid: {
        if (!/^[0-9]{1,5}(-[0-9]{1,5})?$/.test(portInput.text)) return false;
        const bounds = portInput.text.split("-").map(Number);
        return bounds.every(n => n >= 1 && n <= 65535) && bounds[0] <= bounds[bounds.length - 1];
    }

    function goBack() {
        if (pending) return;
        const history = pageHistory.slice();
        const destination = history.pop() || {page:"home", scope, zoneName, section, resourceKind, resourceName};
        pageHistory = history;
        assignmentInterface = "";
        returning = true;
        scope = destination.scope;
        zoneName = destination.zoneName;
        section = destination.section;
        resourceKind = destination.resourceKind;
        resourceName = destination.resourceName;
        page = destination.page;
        returning = false;
    }
    function available(action) { return (stateData.capabilities ?? []).includes(action); }
    function matches(text) { return String(text).toLowerCase().includes(query.toLowerCase()); }
    function scopeTitle(value) { return value === "runtime" ? "Runtime · now" : "Permanent · saved"; }
    function openZone(name) {
        if (pending) return;
        zoneName = name;
        page = "zone";
        advancedOpen = false;
    }
    function openDefinition(kind, name) {
        if (pending || control.busy) return;
        resourceKind = kind;
        resourceName = name;
        page = "definition";
        control.inspect(kind, name, scope);
    }
    function entries(field) {
        const value = String(fields[field] ?? "");
        return (field === "rich rules" || field === "forward-ports" ? value.split("\n") : value.split(/\s+/)).filter(Boolean);
    }
    function review(action, value, extra = {}) {
        if (!control.editable || pending) return;
        if (!extra.global && !extra.connection && !selectedZone) return;
        pending = Object.assign({action, value, scope, zone: zoneName, revision: stateData.revision,
                                interfaces: fields.interfaces || "None", previousZone: ""}, extra);
        scroller.contentY = 0;
    }
    function actionTitle(action) {
        return ({"add-service":"Allow service", "remove-service":"Remove service", "add-port":"Allow port",
                 "remove-port":"Remove port", "change-interface":"Change connection zone",
                 "new-zone":"Create empty zone", "duplicate-zone":"Duplicate zone rules without bindings", "delete-zone":"Delete custom zone", "new-service":"Create empty service definition",
                 "new-ipset":"Create IPv4 hash:ip definition"})[action] || action.replace(/-/g, " ");
    }
    function usage(kind, name) {
        const objects = zones.concat(policies);
        return objects.filter(obj => kind === "service"
            ? String(obj.fields.services || "").split(/\s+/).includes(name) || String(obj.fields["rich rules"] || "").includes('service name="' + name + '"')
            : String(obj.fields.sources || "").split(/\s+/).includes("ipset:" + name) || String(obj.fields["rich rules"] || "").includes('ipset="' + name + '"'))
            .map(obj => obj.name).join(", ") || "No references found in the displayed zones or policies";
    }

    Component.onCompleted: control.active = true
    Component.onDestruction: control.active = false
    onPageChanged: {
        if (page === "home") pageHistory = [];
        else if (!returning && recordedContext?.page) pageHistory = pageHistory.concat([recordedContext]);
        recordedContext = {page, scope, zoneName, section, resourceKind, resourceName};
        scroller.contentY = 0;
    }
    onScopeChanged: {
        if (!returning && recordedContext?.page)
            recordedContext = Object.assign({}, recordedContext, {scope});
    }

    StyledFlickable {
        id: scroller
        anchors.fill: parent
        clip: true
        contentHeight: column.implicitHeight + 40
        objectName: "firewall-scroller"

        ColumnLayout {
            id: column
            spacing: 16
            width: Math.max(0, scroller.width - 40)
            x: 20
            y: 20

            InlineAction {
                objectName: "firewall-back"
                visible: root.page !== "home"
                label: "‹ Back"
                enabled: !root.pending
                onClicked: root.goBack()
            }
            RowLayout {
                Layout.fillWidth: true
                visible: root.page !== "home"
                Label {
                    objectName: "firewall-heading"
                    font.pixelSize: Appearance.font.pixelSize.huge
                    font.weight: Font.DemiBold
                    text: ({home:"Firewall", connections:"Network connections", zones:"Zones and rules",
                            zone:"Zone · " + root.zoneName, section:root.sectionData.title,
                            "zone-details":"Zone details", "zone-create":"Create zone", resources:"Services and IP sets", definition:root.resourceName,
                            catalog: root.resourceKind === "service" ? "Service definitions" : "IP sets",
                            "definition-create":"Create definition", global:"Policies and diagnostics",
                            policies:"Inter-zone policies", diagnostics:"Service diagnostics"})[root.page] || "Firewall"
                }
                Action {
                    visible: root.page === "zones" || root.page === "catalog"
                    objectName: "firewall-create"
                    label: root.page === "zones" ? "Create zone" : "Create definition"
                    enabled: !root.pending && root.control.editable
                    onClicked: { root.scope = "permanent"; root.page = root.page === "zones" ? "zone-create" : "definition-create"; }
                }
                Action {
                    label: "Refresh"
                    objectName: "firewall-refresh"
                    enabled: !root.control.busy && !root.pending
                    onClicked: root.control.refresh()
                }
            }

            Card {
                id: statusCard
                objectName: "firewall-status-card"
                surfaceOpacity: 0.5
                tone: root.stateData.complete ? SettingsCard.Secondary : SettingsCard.Surface
                visible: root.page === "home" || !root.stateData.complete || !!root.control.error || !!root.control.result
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 12
                    MaterialSymbol {
                        text: root.stateData.complete ? "verified_user" : "shield"
                        color: statusCard.foregroundColor
                        iconSize: Appearance.font.pixelSize.huge
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        Label { text: root.connectionText; color: statusCard.foregroundColor; font.weight: Font.DemiBold }
                        Hint {
                            color: statusCard.foregroundColor
                            text: root.control.refreshing ? "Reading configuration…" : "Last read: " + (root.control.lastValidRead ? new Date(root.control.lastValidRead).toLocaleTimeString() : "Never")
                        }
                    }
                    Action {
                        visible: root.page === "home"
                        label: "Refresh"
                        objectName: "firewall-home-refresh"
                        enabled: !root.control.busy && !root.pending
                        onClicked: root.control.refresh()
                    }
                }
                Hint {
                    visible: !!root.control.error
                    color: Appearance.m3colors.m3error
                    text: root.control.error
                }
                Hint {
                    visible: !root.stateData.complete
                    text: "Current configuration is unavailable. Changes are disabled; previous rules are hidden."
                }
                Hint {
                    visible: !!root.control.result
                    text: root.control.result === "applied" ? "Change applied and verified."
                          : root.control.result === "applied-unverified" ? "Change accepted, but verification failed. Read the actual state before making another change."
                          : "Request failed. A change may have taken effect; refresh and inspect before retrying."
                }
                Hint {
                    visible: root.stateData.state === "access-denied"
                    text: "Authentication is handled by the native session prompt. If it was cancelled or unavailable, select Refresh to try again."
                }
            }

            Card {
                visible: !!root.pending
                emphasized: true
                Label { text: "Review firewall change"; font.weight: Font.DemiBold }
                Label {
                    text: root.pending ? (root.pending.global ? "Global definition" : "Zone: " + root.pending.zone)
                        + " · " + root.scopeTitle(root.pending.scope) + "\n" + root.actionTitle(root.pending.action)
                        + (root.pending.name ? " · " + root.pending.name : "")
                        + (root.pending.value ? ": " + root.pending.value : "")
                        + (root.pending.previousZone ? "\nPrevious zone: " + root.pending.previousZone + " → " + root.pending.zone : "")
                        + (!root.pending.global ? "\nInterfaces: " + root.pending.interfaces : "") : ""
                }
                Hint { text: "This can expose services or interrupt access, including remote sessions. External managers may override bindings. Authorization is requested only if needed for this confirmed operation." }
                Hint { text: "Runtime applies immediately and is lost on reload. Permanent is saved for a future reload or service start. No reload or automatic rollback is performed. A definition alone does not permit traffic." }
                Flow {
                    Layout.fillWidth: true
                    spacing: 8
                    Action {
                        label: "Cancel"
                        objectName: "firewall-cancel"
                        enabled: !root.control.busy
                        onClicked: root.pending = null
                    }
                    Action {
                        label: "Confirm change"
                        objectName: "firewall-confirm"
                        enabled: root.control.editable
                        onClicked: {
                            const change = root.pending;
                            root.pending = null;
                            root.control.apply(change);
                        }
                    }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 16
                visible: root.stateData.complete
                enabled: !root.pending

                Card {
                    id: primaryCard
                    property color textColor: "#ffffff"
                    objectName: "firewall-primary-card"
                    surfaceOpacity: 0.5
                    tone: SettingsCard.Primary
                    visible: root.page === "home"
                    Label { text: "Primary connection"; color: primaryCard.textColor; font.weight: Font.DemiBold }
                    ConnectionInfo {
                        visible: !!root.primaryConnection
                        connection: root.primaryConnection ?? ({})
                        compact: true
                        foregroundColor: primaryCard.textColor
                        secondaryColor: primaryCard.textColor
                        linkColor: primaryCard.textColor
                        linkHoverColor: Appearance.colors.colPrimaryContainerHover
                    }
                    Hint { color: primaryCard.textColor; visible: !root.primaryConnection; text: "No primary connection could be established from the default routes. View all discovered connections." }
                }
                RowLayout {
                    Layout.fillWidth: true
                    visible: root.page === "home"
                    Hint { text: "Connection assignments" }
                    Action { label: "View all connections"; objectName: "firewall-all-connections"; onClicked: root.page = "connections" }
                }
                Label {
                    visible: root.page === "home"
                    text: "Configuration"
                    font.weight: Font.DemiBold
                }
                Repeater {
                    model: root.page === "home" ? [
                        {title:"Zones and rules", icon:"hub", detail:"Select a real Firewalld zone and edit its rules.", destination:"zones"},
                        {title:"Network connections", icon:"lan", detail:"Inspect effective zones, bindings and ownership.", destination:"connections"},
                        {title:"Services and IP sets", icon:"apps", detail:"Global definitions and their separate zone assignments.", destination:"resources"},
                        {title:"Policies and diagnostics", icon:"policy", detail:"Global policies, scope differences and service status.", destination:"global"}
                    ] : []
                    delegate: Card {
                        required property var modelData
                        contentPadding: 0
                        NavigationEntry {
                            objectName: "firewall-task-" + modelData.destination
                            title: modelData.title
                            subtitle: modelData.detail
                            symbol: modelData.icon
                            onClicked: root.page = modelData.destination
                        }
                    }
                }

                SegmentedControl {
                    objectName: "firewall-scope-selector"
                    visible: ["zones", "catalog", "policies"].includes(root.page) || (!!root.assignment && ["home", "connections"].includes(root.page))
                    Layout.fillWidth: true
                    currentIndex: root.scope === "runtime" ? 0 : 1
                    model: [{name:"Runtime · now", icon:"bolt"}, {name:"Permanent · saved", icon:"save"}]
                    onActivated: index => root.scope = index === 0 ? "runtime" : "permanent"
                }

                MaterialTextField {
                    Layout.fillWidth: true
                    visible: ["zones", "connections", "catalog", "policies"].includes(root.page)
                    placeholderText: "Filter this page"
                    Accessible.name: placeholderText
                    onTextChanged: root.query = text
                }

                Hint {
                    visible: root.page === "connections"
                    text: "Connection type does not determine its zone. Effective zones below describe runtime; permanent bindings are listed separately. Source rules and policies can further affect traffic."
                }
                Repeater {
                    model: root.page === "connections" ? root.connections.filter(c => root.matches(JSON.stringify(c))) : []
                    delegate: Card {
                        required property var modelData
                        ConnectionInfo { connection: modelData }
                    }
                }
                Hint { visible: root.page === "connections" && root.connections.length === 0; text: "No interfaces discovered. Network inventory tools may be unavailable." }
                Card {
                    visible: !!root.assignment && ["connections", "home"].includes(root.page)
                    Label { text: "Change zone · " + (root.assignment?.interface || ""); font.weight: Font.DemiBold }
                    Hint {
                        text: root.assignment ? "Effective runtime zone: " + root.assignment.zone + " · " + root.assignment.binding
                            + "\nPermanent binding: " + (root.assignment.permanentZone || "None")
                            + "\n" + (root.assignment.assignmentReason || "Only this interface's Firewalld binding will change in the selected scope. External managers may overwrite it.") : ""
                    }
                    StyledComboBox {
                        id: assignmentZone
                        Layout.fillWidth: true
                        model: root.zones.map(z => z.name)
                        Accessible.name: "Destination zone"
                    }
                    Action {
                        label: "Review connection change"
                        enabled: root.control.editable && !!root.assignment?.canAssign && assignmentZone.currentIndex >= 0 && root.available("change-interface")
                        onClicked: root.review("change-interface", root.assignment.interface, {
                            connection: true, zone: assignmentZone.currentText, interfaces: root.assignment.interface,
                            previousZone: root.scope === "runtime" ? root.assignment.zone : (root.assignment.permanentZone || "No permanent binding")
                        })
                    }
                    Hint { visible: !root.available("change-interface"); text: "Interface assignment is unavailable in the installed Firewalld client." }
                    Action { label: "Cancel assignment"; onClicked: root.assignmentInterface = "" }
                }

                Repeater {
                    model: root.page === "zones" ? root.zones.filter(z => root.matches(JSON.stringify(z))) : []
                    delegate: Card {
                        required property var modelData
                        contentPadding: 0
                        NavigationEntry {
                            objectName: "firewall-zone-" + modelData.name
                            title: modelData.name + (modelData.name === root.stateData.defaultZone ? " · Default" : "")
                            symbol: "hub"
                            subtitle: (modelData.fields.description ? modelData.fields.description + "\n" : "")
                                + "Interfaces: " + (modelData.fields.interfaces || "None") + " · Sources: " + (modelData.fields.sources || "None")
                                + "\n" + (modelData.fields.services === undefined ? "Services not reported" : String(modelData.fields.services).split(/\s+/).filter(Boolean).length + " services")
                                + " · " + (modelData.fields.ports === undefined ? "Ports not reported" : String(modelData.fields.ports).split(/\s+/).filter(Boolean).length + " ports")
                            onClicked: root.openZone(modelData.name)
                        }
                    }
                }
                Card {
                    visible: root.page === "zone-create"
                    Label { text: "Create zone"; font.weight: Font.DemiBold }
                    Hint { text: "New definitions are permanent and empty. They become available at runtime after a future reload performed outside this panel." }
                    MaterialTextField { id: zoneInput; Layout.fillWidth: true; placeholderText: "Zone ID (1–17 letters, digits, _ or -)"; Accessible.name: placeholderText }
                    Action {
                        label: "Review new zone"
                        enabled: root.control.editable && root.scope === "permanent" && root.available("new-zone") && /^[A-Za-z0-9_][A-Za-z0-9_-]{0,16}$/.test(zoneInput.text)
                        onClicked: root.review("new-zone", zoneInput.text, {global:true})
                    }
                    Hint { visible: !root.available("new-zone"); text: "Zone creation is unavailable in the installed Firewalld client." }
                    Hint { text: "Open a zone and read its metadata to duplicate rules or delete an unused custom definition. Deletion is blocked for default or vendor zones, unresolved bindings, policies and external profile dependencies." }
                }

                Card {
                    id: zoneContext
                    objectName: "firewall-zone-context"
                    visible: root.zonePage
                    tone: SettingsCard.Secondary
                    emphasized: true
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        Hint { color: zoneContext.foregroundColor; text: root.scopeTitle(root.scope) }
                        Label { color: zoneContext.foregroundColor; text: root.zoneName; font.weight: Font.DemiBold; font.pixelSize: Appearance.font.pixelSize.larger }
                    }
                    Hint { color: zoneContext.foregroundColor; text: "Interfaces: " + (root.fields.interfaces || "None") + "\nSources: " + (root.fields.sources || "None") }
                    Hint { color: zoneContext.foregroundColor; visible: !root.selectedZone; text: "This zone is unavailable in the selected scope. Go back to the zone list to select another zone." }
                    Hint { visible: root.fields.target === "ACCEPT"; color: Appearance.m3colors.m3error; text: "This zone accepts unmatched traffic. Review its bindings carefully." }
                    Action {
                        label: "Zone details and management"
                        objectName: "firewall-zone-management"
                        visible: root.page !== "zone-details"
                        onClicked: root.page = "zone-details"
                    }
                }

                Card {
                    visible: root.page === "zone-details"
                    Label { text: "Configuration fields"; font.weight: Font.DemiBold }
                    Hint { text: Object.keys(root.fields).map(key => key + ": " + (root.fields[key] || "None")).join("\n") }
                    Action {
                        label: "Read zone metadata"
                        enabled: !root.control.busy && !!root.selectedZone && root.available("info-zone")
                        onClicked: root.control.inspect("zone", root.zoneName, root.scope)
                    }
                    Hint {
                        visible: !!root.zoneMetadata
                        text: Object.keys(root.zoneMetadata?.fields ?? {}).map(key => key + ": " + root.zoneMetadata.fields[key]).join("\n")
                            + (root.zoneMetadata?.origin ? "\nOrigin: " + root.zoneMetadata.origin : "")
                            + (root.zoneMetadata?.unavailableReason ? "\n" + root.zoneMetadata.unavailableReason : "")
                            + (root.zoneMetadata?.deletionReason ? "\nDeletion unavailable: " + root.zoneMetadata.deletionReason : "")
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        visible: root.scope === "permanent" && !!root.selectedZone
                        Hint { text: "Duplicate copies the complete permanent rule definition and metadata, without interfaces or sources. Delete checks both scopes, policies and inactive NetworkManager profiles; unresolved dependencies block it." }
                        MaterialTextField { id: duplicateInput; Layout.fillWidth: true; placeholderText: "New zone ID for duplicate"; Accessible.name: placeholderText }
                        Action {
                            label: "Review duplicate…"
                            enabled: root.control.editable && !!root.zoneMetadata?.documentRevision && root.available("new-zone-from-file") && /^[A-Za-z0-9_][A-Za-z0-9_-]{0,16}$/.test(duplicateInput.text)
                            onClicked: root.review("duplicate-zone", duplicateInput.text, {documentRevision:root.zoneMetadata.documentRevision})
                        }
                        Action {
                            label: "Review custom zone deletion…"
                            enabled: root.control.editable && root.zoneMetadata?.deletionAllowed === true && root.zoneMetadata.deletionRevision === root.stateData.revision && root.available("delete-zone") && root.zoneName !== root.stateData.defaultZone
                                && !["runtime", "permanent"].some(value => (root.stateData.scopes?.[value]?.zones ?? []).some(zone => zone.name === root.zoneName && (!!zone.fields.interfaces || !!zone.fields.sources)))
                                && !["runtime", "permanent"].some(value => (root.stateData.scopes?.[value]?.policies ?? []).some(policy => ["ingress-zones", "egress-zones"].some(key => String(policy.fields[key] || "").split(/\s+/).includes(root.zoneName))))
                            onClicked: root.review("delete-zone", null, {documentRevision:root.zoneMetadata.documentRevision})
                        }
                        Hint { text: "Read metadata first to check origin and dependencies. Deletion stays unavailable until these checks pass for the current configuration. Checks run again after confirmation and can refuse deletion without changing the firewall." }
                    }
                }

                Card {
                    visible: root.page === "section" && root.section === "services" && !!root.selectedZone
                    Label { text: "Services"; font.weight: Font.DemiBold }
                    Hint { text: "Allowed incoming services for this zone. Global definitions can contain multiple ports and protocols." }
                    RuleList { field: "services"; removeAction: "remove-service" }
                    StyledComboBox {
                        id: serviceChoice
                        Layout.fillWidth: true
                        Accessible.name: "Service to allow"
                        model: (root.catalog.services ?? []).filter(name => !root.entries("services").includes(name))
                    }
                    Action {
                        label: "Allow service…"
                        enabled: root.control.editable && serviceChoice.currentIndex >= 0
                        onClicked: root.review("add-service", serviceChoice.currentText)
                    }
                }
                Card {
                    visible: root.page === "section" && root.section === "ports" && !!root.selectedZone
                    Label { text: "Ports"; font.weight: Font.DemiBold }
                    RuleList { field: "ports"; removeAction: "remove-port" }
                    MaterialTextField {
                        id: portInput
                        Layout.fillWidth: true
                        objectName: "firewall-port"
                        placeholderText: "Port or range (1–65535)"
                        Accessible.name: placeholderText
                    }
                    Hint { visible: portInput.text.length > 0 && !root.portValid; text: "Enter an ordered port or range within 1–65535."; color: Appearance.m3colors.m3error }
                    SegmentedControl {
                        id: protocolChoice
                        Layout.fillWidth: true
                        model: [{name:"TCP"}, {name:"UDP"}]
                        onActivated: index => currentIndex = index
                    }
                    Action {
                        label: "Allow port…"
                        enabled: root.control.editable && root.portValid
                        onClicked: root.review("add-port", portInput.text + (protocolChoice.currentIndex === 0 ? "/tcp" : "/udp"))
                    }
                }
                Card {
                    visible: root.page === "zone" && !!root.selectedZone
                    objectName: "firewall-common-rules"
                    Label { text: "Common rules"; font.weight: Font.DemiBold }
                    Repeater {
                        model: root.commonSections
                        delegate: NavigationEntry {
                            required property var modelData
                            objectName: "firewall-zone-section-" + modelData.field
                            title: modelData.title
                            subtitle: modelData.detail
                            symbol: modelData.icon
                            summary: root.fields[modelData.field] === undefined ? "Unavailable" : String(root.entries(modelData.field).length)
                            onClicked: { root.section = modelData.field; root.page = "section"; }
                        }
                    }
                }
                Card {
                    visible: root.page === "zone" && !!root.selectedZone
                    Action { objectName: "firewall-advanced-toggle"; label: root.advancedOpen ? "Advanced ▴" : "Advanced ▾"; onClicked: root.advancedOpen = !root.advancedOpen }
                    Repeater {
                        model: root.advancedOpen ? root.sections : []
                        delegate: NavigationEntry {
                            required property var modelData
                            objectName: "firewall-zone-section-" + modelData.field
                            title: modelData.title
                            subtitle: modelData.hint || "Settings for this zone"
                            symbol: "tune"
                            summary: root.fields[modelData.field] === undefined ? "Unavailable" : modelData.field === "masquerade" ? root.fields.masquerade : String(root.entries(modelData.field).length)
                            onClicked: { root.section = modelData.field; root.page = "section"; }
                        }
                    }
                }

                Card {
                    visible: root.page === "section" && !["services", "ports"].includes(root.section) && !!root.selectedZone
                    Label { text: root.sectionData.title || ""; font.weight: Font.DemiBold }
                    Hint {
                        visible: root.section === "icmp-blocks"
                        text: "ICMP blocks: " + (root.fields["icmp-blocks"] || "None") + "\nBlock inversion: " + (root.fields["icmp-block-inversion"] || "no") + ". With inversion enabled, the listed types are allowed and others are blocked. Review this before changing the list."
                    }
                    Hint {
                        visible: root.section === "masquerade"
                        text: "Source address masquerading: " + (root.fields.masquerade || "Unavailable")
                    }
                    Action {
                        visible: root.section === "masquerade"
                        label: root.fields.masquerade === "yes" ? "Disable masquerading…" : "Enable masquerading…"
                        enabled: root.control.editable && root.fields.masquerade !== undefined
                        onClicked: root.review((root.fields.masquerade === "yes" ? "remove-" : "add-") + "masquerade", null)
                    }
                    Hint {
                        visible: root.section === "forward-ports"
                        text: "Port forwarding destinations are read-only. Structured destination editing is unavailable. Intra-zone forwarding is a separate setting: " + (root.fields.forward || "Unavailable")
                    }
                    Action {
                        visible: root.section === "forward-ports"
                        label: "Change intra-zone forwarding…"
                        enabled: root.control.editable && root.fields.forward !== undefined
                        onClicked: root.review((root.fields.forward === "yes" ? "remove-" : "add-") + "forward", null)
                    }
                    Hint { visible: root.section === "interfaces"; text: "Interface bindings are read-only here. Use Network connections to review ownership and change a supported connection's zone." }
                    Action { visible: root.section === "interfaces"; label: "Network connections"; onClicked: root.page = "connections" }
                    Repeater {
                        model: root.section === "masquerade" ? [] : root.entries(root.section)
                        delegate: ColumnLayout {
                            required property string modelData
                            Layout.fillWidth: true
                            Label { text: modelData }
                            Action {
                                label: "Remove…"
                                visible: !!root.sectionData.action
                                enabled: root.control.editable && root.available("remove-" + root.sectionData.action)
                                onClicked: root.review("remove-" + root.sectionData.action, modelData)
                            }
                        }
                    }
                    Hint { visible: root.section !== "masquerade" && root.entries(root.section).length === 0; text: "No entries in this scope" }
                    MaterialTextField {
                        id: advancedValue
                        visible: !!root.sectionData.action && root.section !== "masquerade"
                        Layout.fillWidth: true
                        placeholderText: root.sectionData.hint || "Value"
                        Accessible.name: placeholderText
                    }
                    Hint { visible: root.section === "icmp-blocks"; text: "Available ICMP types: " + (root.catalog.icmptypes ?? []).join(", ") }
                    Action {
                        label: "Review addition…"
                        visible: advancedValue.visible
                        enabled: root.control.editable && !!advancedValue.text && root.available("add-" + root.sectionData.action)
                        onClicked: root.review("add-" + root.sectionData.action, advancedValue.text)
                    }
                    Hint { visible: !!root.sectionData.action && root.section !== "masquerade" && !root.available("add-" + root.sectionData.action); text: "Editing this section is unavailable in the installed Firewalld client." }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    visible: root.page === "resources"
                    spacing: 16
                    Hint { text: "Manage reusable definitions separately from their use in zones." }
                    Repeater {
                        model: [{kind:"service", title:"Service definitions", detail:"Reusable port and protocol definitions. Creating one does not permit traffic.", icon:"apps"},
                                {kind:"ipset", title:"IP sets", detail:"Reusable address sets. A source or rule must reference a set for it to affect traffic.", icon:"dataset"}]
                        delegate: Card {
                            required property var modelData
                            contentPadding: 0
                            NavigationEntry {
                                objectName: "firewall-catalog-" + modelData.kind
                                title: modelData.title
                                subtitle: modelData.detail
                                symbol: modelData.icon
                                onClicked: { root.resourceKind = modelData.kind; root.page = "catalog"; }
                            }
                        }
                    }
                }
                Card {
                    visible: root.page === "catalog"
                    Hint { text: "Defining a service does not permit traffic. An IP set has no effect until referenced by a source or rule. Definitions and zone assignments are separate." }
                    Hint {
                        visible: root.resourceKind === "ipset" && root.catalog.ipsets === undefined || root.resourceKind === "ipset" && root.catalog.ipsets === null
                        text: "IP set enumeration is unavailable in the installed Firewalld client."
                    }
                    Repeater {
                        model: (root.resourceKind === "service" ? (root.catalog.services ?? []) : (root.catalog.ipsets ?? [])).filter(name => root.matches(name))
                        delegate: NavigationEntry {
                            required property string modelData
                            objectName: "firewall-definition-" + modelData
                            title: modelData
                            subtitle: root.usage(root.resourceKind, modelData)
                            symbol: root.resourceKind === "service" ? "apps" : "dataset"
                            enabled: !root.control.busy && root.available("info-" + root.resourceKind)
                            onClicked: root.openDefinition(root.resourceKind, modelData)
                        }
                    }
                    Hint { visible: !root.available("info-" + root.resourceKind); text: "Definition inspection is unavailable in the installed Firewalld client." }
                }
                Card {
                    visible: root.page === "definition-create"
                    Label { text: root.resourceKind === "service" ? "New service definition" : "New IP set"; font.weight: Font.DemiBold }
                    MaterialTextField { id: definitionInput; Layout.fillWidth: true; placeholderText: "Definition ID (1–17 letters, digits, _ or -)"; Accessible.name: placeholderText }
                    Hint { text: "New services are empty. New IP sets use hash:ip, IPv4, without a timeout. Definitions are created only in permanent configuration." }
                    Action {
                        label: "Review new definition…"
                        enabled: root.control.editable && root.scope === "permanent" && root.available("new-" + root.resourceKind) && /^[A-Za-z0-9_][A-Za-z0-9_-]{0,16}$/.test(definitionInput.text)
                        onClicked: root.review("new-" + root.resourceKind, definitionInput.text, {global:true})
                    }
                    Hint { visible: !root.available("new-" + root.resourceKind); text: "Definition creation is unavailable in the installed Firewalld client." }
                }
                Card {
                    visible: root.page === "definition"
                    Label { text: root.resourceKind + " · " + root.resourceName + " · " + root.scopeTitle(root.scope); font.weight: Font.DemiBold }
                    Hint { text: "Defining this object does not allow traffic. Assignment to a zone or reference from a rule is separate." }
                    Action { label: "Read definition"; enabled: !root.control.busy; onClicked: root.control.inspect(root.resourceKind, root.resourceName, root.scope) }
                    Hint { visible: !root.definition; text: "Definition not loaded for this scope. Read it explicitly to inspect or edit." }
                    Hint { text: Object.keys(root.definition?.fields ?? {}).map(key => key + ": " + (root.definition.fields[key] || "None")).join("\n") }
                    Label { text: "Usage in this scope"; font.weight: Font.DemiBold }
                    Hint { text: root.usage(root.resourceKind, root.resourceName) + ". Review full rich rules for indirect references." }
                    Action {
                        label: "Assign in zone…"
                        onClicked: root.page = "zones"
                    }
                    Hint { text: "For services, select a zone and allow the service. For IP sets, select a zone → Advanced → Sources, and add ipset:" + root.resourceName + ". Adding a source changes which traffic is classified into that zone." }
                    MaterialTextField {
                        id: definitionValue
                        Layout.fillWidth: true
                        placeholderText: root.resourceKind === "service" ? "Port or range with /tcp or /udp" : "IPv4 address (hash:ip without timeout only)"
                        Accessible.name: placeholderText
                    }
                    Flow {
                        Layout.fillWidth: true
                        spacing: 8
                        Repeater {
                            model: ["add", "remove"]
                            delegate: Action {
                                required property string modelData
                                label: modelData === "add" ? "Review addition…" : "Review removal…"
                                enabled: root.control.editable && root.definitionEditable && !!definitionValue.text && root.available(modelData + (root.resourceKind === "service" ? "-port" : "-entry"))
                                onClicked: root.review("definition-" + modelData + (root.resourceKind === "service" ? "-port" : "-entry"), definitionValue.text, {global:true, name:root.resourceName, definitionRevision:root.definition.revision})
                            }
                        }
                    }
                    Hint { visible: !!root.definition && !root.definitionEditable; text: "Editing is available only for permanent services or IPv4 hash:ip sets without timeouts. This definition remains available for inspection." }
                    Hint { text: "Definition deletion and duplication are unavailable: origin and dependencies across other definitions and external tools are not yet verified. Complex service fields and other IP set types are inspected without rewriting them." }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    visible: root.page === "global"
                    spacing: 16
                    Hint { text: "Firewall-wide information, separate from rules in an individual zone." }
                    Repeater {
                        model: [{destination:"policies", title:"Inter-zone policies", detail:"Inspect traffic direction, targets and rules between zones.", icon:"policy"},
                                {destination:"diagnostics", title:"Service diagnostics", detail:"Connection status, configuration differences and errors.", icon:"info"}]
                        delegate: Card {
                            required property var modelData
                            contentPadding: 0
                            NavigationEntry {
                                objectName: "firewall-global-" + modelData.destination
                                title: modelData.title
                                subtitle: modelData.detail
                                symbol: modelData.icon
                                onClicked: root.page = modelData.destination
                            }
                        }
                    }
                }
                Card {
                    visible: root.page === "diagnostics"
                    Label { text: "Global status"; font.weight: Font.DemiBold }
                    Hint { text: "Default zone: " + root.stateData.defaultZone + "\nZones with runtime/permanent differences: " + ((root.stateData.differences ?? []).join(", ") || "None") }
                    Hint { text: "Differences can include bindings maintained by other tools. No reload, daemon control or bulk runtime-to-permanent operation is performed here. Global policy editing is unavailable; inspect the complete policy fields below." }
                    Hint { text: "Service status is not a security audit. Last complete read: " + (root.control.lastValidRead || "Never") }
                }
                Card {
                    visible: root.page === "policies"
                    Label { text: "Policies between zones"; font.weight: Font.DemiBold }
                    Hint { text: "Policy editing is unavailable in this panel. Complete policy fields are preserved below." }
                    Hint { visible: root.policies.length === 0; text: "No policies in this scope" }
                    Repeater {
                        model: root.policies.filter(policy => root.matches(JSON.stringify(policy)))
                        delegate: ColumnLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            Label { text: modelData.name; font.weight: Font.DemiBold }
                            Hint { text: Object.keys(modelData.fields).map(key => key + ": " + (modelData.fields[key] || "None")).join("\n") }
                        }
                    }
                    Hint { text: "Ingress and egress define direction. HOST means this machine; ANY means any zone. Zone controls are separate from these global policies." }
                }
            }
        }
    }

    component ConnectionInfo: ColumnLayout {
        id: connectionInfo
        required property var connection
        property bool compact: false
        property color foregroundColor: Appearance.colors.colOnLayer0
        property color secondaryColor: Appearance.colors.colSubtext
        property color linkColor: Appearance.colors.colPrimary
        property color linkHoverColor: Appearance.colors.colLayer0Hover
        objectName: "firewall-connection-info"
        Layout.fillWidth: true
        spacing: 8

        GridLayout {
            id: connectionGrid
            Layout.fillWidth: true
            columns: width >= Appearance.font.pixelSize.normal * 33 ? 2 : 1
            columnSpacing: 16
            rowSpacing: 8
            RowLayout {
                Layout.fillWidth: true
                spacing: 12
                MaterialSymbol {
                    text: connectionInfo.connection.type === "wifi" ? "wifi" : "lan"
                    color: connectionInfo.linkColor
                    iconSize: Appearance.font.pixelSize.huge
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    spacing: 4
                    Label {
                        color: connectionInfo.foregroundColor
                        text: (connectionInfo.connection.name || connectionInfo.connection.interface || "")
                            + (connectionInfo.connection.name && connectionInfo.connection.name !== connectionInfo.connection.interface ? " · " + connectionInfo.connection.interface : "")
                        font.weight: Font.DemiBold
                    }
                    Hint { color: connectionInfo.secondaryColor; text: (connectionInfo.connection.type || "Unknown type") + " · " + (connectionInfo.connection.status || "Unknown status") }
                    InlineAction {
                        objectName: "firewall-zone-link-" + (connectionInfo.connection.interface || "unknown")
                        label: "Zone · " + (connectionInfo.connection.zone || "Unknown") + " ↗"
                        foregroundColor: connectionInfo.linkColor
                        colBackgroundHover: connectionInfo.linkHoverColor
                        enabled: !!connectionInfo.connection.zone
                        onClicked: { root.scope = "runtime"; root.openZone(connectionInfo.connection.zone); }
                    }
                }
            }
            Action {
                label: "Change zone"
                Layout.alignment: connectionGrid.columns === 1 ? Qt.AlignLeft : Qt.AlignRight
                onClicked: root.assignmentInterface = connectionInfo.connection.interface
            }
        }
        Hint {
            visible: !connectionInfo.compact
            color: connectionInfo.secondaryColor
            text: "Manager: " + (connectionInfo.connection.manager || "Unknown")
                + "\nBinding: " + (connectionInfo.connection.binding === "default" ? "Inherited default zone" : "Reported Firewalld interface binding")
                + " · Permanent: " + (connectionInfo.connection.permanentZone || "None")
        }
    }
    component InlineAction: RippleButton {
        id: link
        property string label: ""
        property color foregroundColor: Appearance.colors.colPrimary
        Accessible.name: label
        implicitWidth: linkText.implicitWidth + leftPadding + rightPadding
        implicitHeight: linkText.implicitHeight + topPadding + bottomPadding
        Layout.maximumWidth: parent.width
        leftPadding: Appearance.font.pixelSize.smaller
        rightPadding: Appearance.font.pixelSize.smaller
        topPadding: 4
        bottomPadding: 4
        colBackground: "transparent"
        contentItem: StyledText {
            id: linkText
            text: link.label
            textFormat: Text.PlainText
            color: link.foregroundColor
            wrapMode: Text.Wrap
        }
    }
    component NavigationEntry: RippleButton {
        id: entry
        property string title: ""
        property string subtitle: ""
        property string symbol: "chevron_right"
        property string summary: ""

        Layout.fillWidth: true
        implicitHeight: Math.max(Appearance.font.pixelSize.normal * 4, row.implicitHeight + 24)
        Accessible.name: title
        leftPadding: 16
        rightPadding: 16
        topPadding: 12
        bottomPadding: 12
        colBackground: "transparent"
        colBackgroundHover: Appearance.colors.colLayer0Hover

        contentItem: RowLayout {
            id: row
            spacing: 12
            MaterialSymbol { text: entry.symbol; color: Appearance.colors.colPrimary; iconSize: Appearance.font.pixelSize.huge }
            ColumnLayout {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                spacing: 4
                Label { text: entry.title; font.weight: Font.DemiBold }
                Hint { text: entry.subtitle; visible: text.length > 0 }
            }
            Hint { text: entry.summary; visible: text.length > 0; Layout.fillWidth: false }
            MaterialSymbol { text: "chevron_right"; color: Appearance.colors.colSubtext; iconSize: Appearance.font.pixelSize.larger }
        }
    }
    component Action: RippleButton {
        id: button

        property string label: ""

        Accessible.name: label
        colBackground: Appearance.colors.colSecondaryContainer
        colBackgroundHover: Appearance.colors.colSecondaryContainerHover
        implicitHeight: 40
        implicitWidth: buttonText.implicitWidth + 28

        contentItem: StyledText {
            id: buttonText

            color: button.enabled ? Appearance.colors.colOnSecondaryContainer : Appearance.colors.colSubtext
            horizontalAlignment: Text.AlignHCenter
            text: button.label
            verticalAlignment: Text.AlignVCenter
        }
    }
    component Card: SettingsCard {
        default property alias content: body.data

        property real contentPadding: 16
        Layout.fillWidth: true
        implicitHeight: body.implicitHeight + contentPadding * 2
        objectName: "firewall-card"

        ColumnLayout {
            id: body

            spacing: 12

            anchors {
                left: parent.left
                margins: parent.contentPadding
                right: parent.right
                top: parent.top
            }
        }
    }
    component Hint: Label {
        color: Appearance.colors.colSubtext
        font.pixelSize: Appearance.font.pixelSize.small
    }
    component Label: StyledText {
        Layout.fillWidth: true
        color: Appearance.colors.colOnLayer0
        textFormat: Text.PlainText
        wrapMode: Text.Wrap
    }
    component RuleList: ColumnLayout {
        id: rules

        readonly property var entries: String(root.fields[field] ?? "").split(/\s+/).filter(Boolean)
        required property string field
        readonly property var filteredEntries: entries.filter(value => root.matches(value))
        required property string removeAction

        Layout.fillWidth: true
        spacing: 4

        Hint {
            text: Translation.tr("No rules in this scope")
            visible: rules.entries.length === 0
        }

        Hint {
            text: Translation.tr("No matching rules")
            visible: rules.entries.length > 0 && rules.filteredEntries.length === 0
        }

        Repeater {
            model: rules.filteredEntries

            delegate: RowLayout {
                id: rule

                required property string modelData

                Layout.fillWidth: true

                Label {
                    text: rule.modelData
                }

                Action {
                    enabled: root.control.editable && !root.pending
                    label: Translation.tr("Remove")

                    onClicked: root.review(rules.removeAction, rule.modelData)
                }
            }
        }
    }
}
