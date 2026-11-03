pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import qs.services
import qs.modules.shared
import qs.modules.shared.primitives.common
import qs.modules.shared.widgets
ColumnLayout {
    id: root
    property var flags: ({})
    property var argumentsList: []
    property bool confirmed: false
    property bool administrator: false
    property bool showHelp: false
    readonly property bool selected: TailscaleControl.commandPath.length > 0
    spacing: 12
    Component.onCompleted: TailscaleControl.selectCommand([])
    Connections {
        target: TailscaleControl
        function onSchemaChanged() { root.flags = ({}); root.argumentsList = []; root.confirmed = false; search.clear(); root.showHelp = false; }
    }
    function setOption(name, value, include) {
        const next = Object.assign({}, flags);
        if (include) next[name] = value; else delete next[name];
        flags = next; confirmed = false;
    }
    function commandIcon(name) {
        return ({up:"link", down:"link_off", set:"tune", get:"manage_search", login:"login", logout:"logout", switch:"switch_account", configure:"build", debug:"bug_report", status:"monitor_heart", ping:"network_ping", netcheck:"speed", dns:"dns", ip:"lan", ssh:"terminal", nc:"terminal", serve:"share", funnel:"public", file:"folder_shared", cert:"verified_user", lock:"lock", update:"system_update", web:"web", metrics:"monitoring", version:"info", drive:"hard_drive", service:"dns", whois:"person_search", whoami:"account_circle", "exit-node":"alt_route"})[name] || "terminal";
    }
    RowLayout {
        Layout.fillWidth: true
        RippleButtonWithIcon { materialIcon: "arrow_back"; mainText: ""; enabled: root.selected; onClicked: TailscaleControl.selectCommand(TailscaleControl.commandPath.slice(0, -1)); Accessible.name: Translation.tr("Back") }
        ColumnLayout {
            Layout.fillWidth: true; spacing: 2
            StyledText { Layout.fillWidth: true; text: root.selected ? "tailscale " + TailscaleControl.commandPath.join(" ") : Translation.tr("Command center"); textFormat: Text.PlainText; elide: Text.ElideRight; font.weight: Font.DemiBold; font.pixelSize: Appearance.font.pixelSize.large }
            StyledText { Layout.fillWidth: true; text: root.selected ? Translation.tr("Configure only the options you want to send") : Translation.tr("Explore the tools available in your installed Tailscale CLI"); color: Appearance.colors.colSubtext; wrapMode: Text.WordWrap; font.pixelSize: Appearance.font.pixelSize.smaller }
        }
        RippleButtonWithIcon { visible: root.selected; materialIcon: "help_outline"; mainText: Translation.tr("Help"); toggled: root.showHelp; onClicked: root.showHelp = !root.showHelp }
    }
    MaterialTextField { id: search; Layout.fillWidth: true; placeholderText: Translation.tr("Search commands and options"); wrapMode: TextInput.NoWrap }
    TailscaleCard {
        visible: root.showHelp
        title: Translation.tr("Command help"); icon: "info"
        StyledText { Layout.fillWidth: true; text: TailscaleControl.schema.description + "\n\n" + TailscaleControl.schema.usage; textFormat: Text.PlainText; wrapMode: Text.WordWrap; color: Appearance.colors.colSubtext; font.pixelSize: Appearance.font.pixelSize.smaller }
    }
    GridLayout {
        Layout.fillWidth: true
        columns: root.width >= 850 ? 3 : root.width >= 560 ? 2 : 1
        columnSpacing: 8; rowSpacing: 8
        Repeater {
            model: TailscaleControl.schema.children.filter(c => (c.name + " " + c.description).toLowerCase().includes(search.text.toLowerCase()))
            RippleButton {
                id: command
                required property var modelData
                Layout.fillWidth: true
                implicitHeight: 72
                buttonRadius: Appearance.rounding.small
                colBackground: Appearance.colors.colLayer1
                onClicked: TailscaleControl.selectCommand([...TailscaleControl.commandPath, modelData.name])
                contentItem: RowLayout {
                    spacing: 10
                    MaterialSymbol { text: root.commandIcon(command.modelData.name); iconSize: 24; color: Appearance.colors.colPrimary }
                    ColumnLayout {
                        Layout.fillWidth: true; spacing: 3
                        StyledText { Layout.fillWidth: true; text: command.modelData.name; textFormat: Text.PlainText; font.weight: Font.DemiBold; elide: Text.ElideRight }
                        StyledText { Layout.fillWidth: true; text: command.modelData.description; textFormat: Text.PlainText; color: Appearance.colors.colSubtext; font.pixelSize: Appearance.font.pixelSize.smaller; elide: Text.ElideRight }
                    }
                    MaterialSymbol { text: "chevron_right"; iconSize: 18; color: Appearance.colors.colSubtext }
                }
            }
        }
    }
    GridLayout {
        Layout.fillWidth: true
        columns: root.width >= 780 ? 2 : 1
        columnSpacing: 10; rowSpacing: 10
        Repeater {
            model: TailscaleControl.schema.flags.filter(f => root.selected && (f.name + " " + f.description).toLowerCase().includes(search.text.toLowerCase()))
            TailscaleCard {
                id: option
                required property var modelData
                Layout.alignment: Qt.AlignTop
                readonly property bool included: Object.prototype.hasOwnProperty.call(root.flags, modelData.name)
                readonly property bool numeric: modelData.input === "number"
                emphasized: included
                padding: 12
                function currentValue() { return modelData.type === "bool" ? boolValue.checked : numeric ? String(number.value) : value.text; }
                RowLayout {
                    Layout.fillWidth: true
                    MaterialSymbol { text: option.modelData.secret ? "key" : option.modelData.type === "bool" ? "toggle_on" : option.numeric ? "tag" : "edit_note"; iconSize: 20; color: option.included ? Appearance.colors.colPrimary : Appearance.colors.colSubtext }
                    StyledText { Layout.fillWidth: true; text: option.modelData.name; textFormat: Text.PlainText; elide: Text.ElideRight; font.weight: Font.Medium }
                    StyledSwitch { checked: option.included; onToggled: root.setOption(option.modelData.name, option.currentValue(), checked); Accessible.name: Translation.tr("Include option") + " " + option.modelData.name }
                }
                StyledText { Layout.fillWidth: true; text: option.modelData.description; textFormat: Text.PlainText; wrapMode: Text.WordWrap; color: Appearance.colors.colSubtext; font.pixelSize: Appearance.font.pixelSize.smaller }
                RowLayout {
                    visible: option.included && option.modelData.type === "bool"
                    StyledText { Layout.fillWidth: true; text: boolValue.checked ? Translation.tr("Enabled") : Translation.tr("Disabled"); color: Appearance.colors.colSubtext }
                    StyledSwitch { id: boolValue; checked: root.flags[option.modelData.name] === true; onToggled: root.setOption(option.modelData.name, checked, option.included) }
                }
                RowLayout {
                    visible: option.included && option.numeric
                    StyledSpinBox { id: number; Layout.fillWidth: true; from: option.modelData.minimum ?? 0; to: option.modelData.maximum ?? 2147483647; value: option.numeric ? Number(root.flags[option.modelData.name] ?? from) : 0; onValueChanged: if (option.numeric && option.included && String(value) !== root.flags[option.modelData.name]) root.setOption(option.modelData.name, String(value), true) }
                    StyledText { text: (option.modelData.minimum ?? 0) + " … " + (option.modelData.maximum ?? 2147483647); color: Appearance.colors.colSubtext; font.pixelSize: Appearance.font.pixelSize.smaller }
                }
                MaterialTextField { id: value; Layout.fillWidth: true; visible: option.included && option.modelData.type !== "bool" && !option.numeric; text: String(root.flags[option.modelData.name] ?? ""); wrapMode: TextInput.NoWrap; echoMode: option.modelData.secret ? TextInput.Password : TextInput.Normal; onTextEdited: root.setOption(option.modelData.name, text, option.included) }
            }
        }
    }
    TailscaleCard {
        visible: root.selected
        title: Translation.tr("Arguments & execution"); icon: "play_circle"
        subtitle: TailscaleControl.schema.usage
        Repeater {
            model: root.argumentsList.length
            RowLayout {
                id: argument
                required property int index
                Layout.fillWidth: true
                TailscaleBadge { text: String(argument.index + 1); icon: "tag" }
                MaterialTextField { Layout.fillWidth: true; text: root.argumentsList[argument.index]; placeholderText: Translation.tr("Argument") + " " + (argument.index + 1); wrapMode: TextInput.NoWrap; onTextEdited: { const next = root.argumentsList.slice(); next[argument.index] = text; root.argumentsList = next; root.confirmed = false; } }
                RippleButtonWithIcon { materialIcon: "close"; mainText: ""; onClicked: { root.argumentsList = root.argumentsList.filter((_, i) => i !== argument.index); root.confirmed = false; } Accessible.name: Translation.tr("Remove argument") }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            RippleButtonWithIcon { materialIcon: "add"; mainText: Translation.tr("Add argument"); onClicked: { root.argumentsList = [...root.argumentsList, ""]; root.confirmed = false; } }
            Item { Layout.fillWidth: true }
            MaterialSymbol { text: "admin_panel_settings"; iconSize: 20; color: Appearance.colors.colSubtext }
            StyledText { text: Translation.tr("Administrator"); color: Appearance.colors.colSubtext }
            StyledSwitch { checked: root.administrator; onToggled: { root.administrator = checked; root.confirmed = false; } }
        }
        RowLayout {
            Layout.fillWidth: true
            MaterialSymbol { text: "info"; iconSize: 20; color: Appearance.colors.colSubtext }
            StyledText { Layout.fillWidth: true; text: Translation.tr("Arguments are passed individually. These operations may change connectivity, remove accounts or expose services. Review the command help before running."); color: Appearance.colors.colSubtext; font.pixelSize: Appearance.font.pixelSize.smaller; wrapMode: Text.WordWrap }
        }
        RowLayout {
            Layout.fillWidth: true
            StyledSwitch { checked: root.confirmed; onToggled: root.confirmed = checked }
            StyledText { Layout.fillWidth: true; text: Translation.tr("I reviewed this operation"); wrapMode: Text.WordWrap }
            RippleButtonWithIcon { materialIcon: "play_arrow"; mainText: Translation.tr("Run operation"); toggled: true; enabled: root.confirmed && !TailscaleControl.busy && !TailscaleControl.schemaLoading && root.selected; onClicked: { TailscaleControl.run(TailscaleControl.commandPath, root.flags, root.argumentsList, root.administrator); root.confirmed = false; } }
        }
    }
}
