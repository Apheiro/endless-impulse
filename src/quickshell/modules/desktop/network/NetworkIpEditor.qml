pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets

ColumnLayout {
    id: root
    objectName: ipv6 ? "network-ipv6-editor" : "network-ipv4-editor"
    required property var settings
    property bool ipv6: false
    property bool wireguard: false
    property bool routesOpen: false
    readonly property var methods: wireguard ? (ipv6 ? ["manual", "disabled", "ignore"] : ["manual", "disabled"]) : ipv6 ? ["auto", "manual", "dhcp", "link-local", "shared", "disabled", "ignore"] : ["auto", "manual", "link-local", "shared", "disabled"]
    readonly property string selectedMethod: methods[method.currentIndex] || "auto"
    readonly property bool enabledFamily: !["disabled", "ignore"].includes(selectedMethod)
    readonly property var methodLabels: ({auto: Translation.tr("Automatic (DHCP / router)"), manual: Translation.tr("Manual — static IP"), dhcp: Translation.tr("DHCP only"), "link-local": Translation.tr("Local link only"), shared: Translation.tr("Share this connection"), disabled: Translation.tr("Disabled"), ignore: Translation.tr("Leave unmanaged")})
    property ListModel routeModel: ListModel {}
    Layout.fillWidth: true
    spacing: 12
    function list(value) { return value.split(/[\n,]+/).map(item => item.trim()).filter(item => item.length); }
    function routeValues() { return Array.from({length: routeModel.count}, (_, i) => ({destination: routeModel.get(i).destination, gateway: routeModel.get(i).gateway, metric: Number(routeModel.get(i).metric)})); }
    function changes() {
        const current = {method: selectedMethod, addresses: list(addresses.text), gateway: gateway.text.trim(), dns: list(dns.text), domains: list(domains.text), ignoreAutoDns: ignoreDns.checked, neverDefault: neverDefault.checked, metric: Number(metric.text)};
        const result = {};
        for (const [key, value] of Object.entries(current)) if (JSON.stringify(value) !== JSON.stringify(settings[key])) result[key] = value;
        const routes = routeValues();
        if (JSON.stringify(routes) !== JSON.stringify(settings.routes || [])) result.routes = routes;
        return result;
    }
    Component.onCompleted: {
        method.currentIndex = Math.max(0, methods.indexOf(settings.method || "auto"));
        addresses.text = (settings.addresses || []).join(", "); gateway.text = settings.gateway || "";
        dns.text = (settings.dns || []).join(", "); domains.text = (settings.domains || []).join(", ");
        metric.text = String(settings.metric ?? -1); ignoreDns.checked = !!settings.ignoreAutoDns; neverDefault.checked = !!settings.neverDefault;
        for (const route of settings.routes || []) routeModel.append({destination: route.destination, gateway: route.gateway || "", metric: String(route.metric ?? -1)});
    }
    NetworkEditorSection {
        title: root.ipv6 ? Translation.tr("IPv6 addressing") : Translation.tr("IPv4 addressing")
        icon: "lan"
        description: root.ipv6 ? Translation.tr("Configure IPv6 independently from IPv4.") : Translation.tr("Choose automatic addressing or enter the static addresses supplied by your network.")
        StyledText { text: Translation.tr("Address assignment"); font.pixelSize: Appearance.font.pixelSize.small }
        StyledComboBox { id: method; Layout.fillWidth: true; model: root.methods.map(id => ({name: root.methodLabels[id], id: id})); textRole: "name" }
        ColumnLayout {
            Layout.fillWidth: true
            visible: root.enabledFamily
            StyledText { text: root.selectedMethod === "manual" ? Translation.tr("Static addresses / prefix") : Translation.tr("Additional addresses / prefix (optional)"); font.pixelSize: Appearance.font.pixelSize.small }
            MaterialTextField { id: addresses; objectName: root.ipv6 ? "ipv6-addresses" : "ipv4-addresses"; Layout.fillWidth: true; wrapMode: TextInput.NoWrap; placeholderText: root.ipv6 ? "2001:db8::20/64" : "192.168.1.20/24" }
            StyledText { text: Translation.tr("Gateway (optional)"); font.pixelSize: Appearance.font.pixelSize.small }
            MaterialTextField { id: gateway; Layout.fillWidth: true; wrapMode: TextInput.NoWrap; placeholderText: root.ipv6 ? "2001:db8::1" : "192.168.1.1" }
        }
    }
    NetworkEditorSection {
        visible: root.enabledFamily
        title: Translation.tr("DNS & search domains")
        icon: "dns"
        description: Translation.tr("Separate multiple values with commas. Empty fields keep automatic DNS when enabled below.")
        RowLayout { Layout.fillWidth: true; StyledSwitch { id: ignoreDns } StyledText { Layout.fillWidth: true; text: Translation.tr("Use only custom DNS servers"); wrapMode: Text.WordWrap } }
        StyledText { text: Translation.tr("DNS servers"); font.pixelSize: Appearance.font.pixelSize.small }
        MaterialTextField { id: dns; Layout.fillWidth: true; wrapMode: TextInput.NoWrap; placeholderText: root.ipv6 ? "2606:4700:4700::1111" : "1.1.1.1, 9.9.9.9" }
        StyledText { text: Translation.tr("Search domains (optional)"); font.pixelSize: Appearance.font.pixelSize.small }
        MaterialTextField { id: domains; Layout.fillWidth: true; wrapMode: TextInput.NoWrap; placeholderText: "example.internal" }
    }
    NetworkEditorSection {
        visible: root.enabledFamily
        title: Translation.tr("Routing")
        icon: "route"
        RowLayout { Layout.fillWidth: true; StyledSwitch { id: neverDefault } StyledText { Layout.fillWidth: true; text: Translation.tr("Never use this connection as the default route"); wrapMode: Text.WordWrap } }
        StyledText { text: Translation.tr("Route priority (−1 = automatic; lower values take priority)"); wrapMode: Text.WordWrap; Layout.fillWidth: true; font.pixelSize: Appearance.font.pixelSize.small }
        MaterialTextField { id: metric; Layout.fillWidth: true; wrapMode: TextInput.NoWrap; validator: DoubleValidator { bottom: -1; top: 4294967295; decimals: 0; notation: DoubleValidator.StandardNotation } }
        RippleButtonWithIcon { materialIcon: root.routesOpen ? "expand_less" : "expand_more"; mainText: Translation.tr("Static routes") + " (" + root.routeModel.count + ")"; onClicked: root.routesOpen = !root.routesOpen }
        ColumnLayout {
            visible: root.routesOpen
            Layout.fillWidth: true
            Repeater {
                model: root.routeModel
                delegate: ColumnLayout {
                    id: route
                    required property int index
                    required property string destination
                    required property string gateway
                    required property string metric
                    Layout.fillWidth: true
                    RowLayout {
                        Layout.fillWidth: true
                        StyledText { Layout.fillWidth: true; text: Translation.tr("Route ") + (route.index + 1); color: Appearance.colors.colSubtext; font.pixelSize: Appearance.font.pixelSize.small }
                        RippleButtonWithIcon { materialIcon: "delete"; mainText: ""; onClicked: root.routeModel.remove(route.index) }
                    }
                    MaterialTextField { Layout.fillWidth: true; text: route.destination; wrapMode: TextInput.NoWrap; placeholderText: Translation.tr("Destination / prefix"); onTextEdited: root.routeModel.setProperty(route.index, "destination", text) }
                    RowLayout {
                        Layout.fillWidth: true
                        MaterialTextField { Layout.fillWidth: true; text: route.gateway; wrapMode: TextInput.NoWrap; placeholderText: Translation.tr("Gateway (optional)"); onTextEdited: root.routeModel.setProperty(route.index, "gateway", text) }
                        MaterialTextField { Layout.preferredWidth: 110; text: route.metric; wrapMode: TextInput.NoWrap; placeholderText: Translation.tr("Metric"); validator: DoubleValidator { bottom: -1; top: 4294967295; decimals: 0; notation: DoubleValidator.StandardNotation } onTextEdited: root.routeModel.setProperty(route.index, "metric", text) }
                    }
                }
            }
            RippleButtonWithIcon { materialIcon: "add"; mainText: Translation.tr("Add route"); onClicked: root.routeModel.append({destination: "", gateway: "", metric: "-1"}) }
        }
    }
}
