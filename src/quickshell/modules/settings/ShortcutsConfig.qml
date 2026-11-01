pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland
import qs.services
import qs.modules.common
import qs.modules.common.widgets
import "../common/functions/ShortcutSymbols.js" as ShortcutSymbols

SettingsPage {
    id: root
    forceWidth: true
    property var shortcuts: []
    property string message: ""
    property bool failed: false
    property bool refreshPending: false
    property string selectedId: ""
    property string selectedDefault: ""
    property bool selectedModified: false
    property string editedCombination: ""
    property var expandedCategories: ({})
    property bool showGuide: false
    property string storePath: Directories.shellConfig + "/shortcuts.lua"
    property string storeDirectory: Directories.shellConfig
    property bool storeExists: false
    readonly property var groups: ShortcutSymbols.groups(shortcuts, search.text)
    readonly property int visibleCount: groups.reduce((count, group) => count + group.entries.length, 0)
    property string helperPath: Quickshell.shellPath("scripts/hyprland/shortcuts.py")

    function expanded(name) { return search.text.trim() !== "" || !!expandedCategories[name]; }
    function toggleCategory(name) {
        const next = Object.assign({}, expandedCategories);
        next[name] = !expanded(name);
        expandedCategories = next;
    }
    function select(entry) {
        selectedId = selectedId === entry.id ? "" : entry.id;
        selectedDefault = entry.default;
        selectedModified = entry.modified;
        editedCombination = entry.current;
    }
    function details(entry) {
        return (entry.description || entry.default) + "\n" + entry.current
            + (entry.modified ? " · " + Translation.tr("Customized") : "")
            + (entry.submap ? " · " + entry.submap : "")
            + (entry.count > 1 ? " · " + entry.count + " " + Translation.tr("linked actions") : "");
    }
    function request(action, identifier, combination) {
        if (worker.running) return;
        let args = ["python3", helperPath, action];
        if (identifier !== undefined) args.push(identifier);
        if (combination !== undefined) args.push(combination);
        failed = false;
        message = action === "list" ? Translation.tr("Loading shortcuts…") : Translation.tr("Applying shortcut…");
        worker.command = args;
        worker.running = true;
    }
    Component.onCompleted: request("list")
    Connections {
        target: Hyprland
        function onRawEvent(event) {
            if (event.name !== "configreloaded") return;
            if (worker.running) root.refreshPending = true;
            else refreshTimer.restart();
        }
    }
    Timer { id: refreshTimer; interval: 200; onTriggered: root.request("list") }
    Process {
        id: worker
        property bool receivedResponse: false
        onStarted: receivedResponse = false
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const result = JSON.parse(text);
                    worker.receivedResponse = true;
                    root.failed = !result.ok;
                    if (result.ok) {
                        root.shortcuts = result.shortcuts;
                        root.storePath = result.store || root.storePath;
                        root.storeDirectory = result.directory || root.storeDirectory;
                        root.storeExists = result.storeExists ?? false;
                        root.message = Translation.tr("Shortcuts are up to date.");
                        const selected = result.shortcuts.find(entry => entry.id === root.selectedId);
                        if (selected) {
                            root.editedCombination = selected.current;
                            root.selectedModified = selected.modified;
                        } else root.selectedId = "";
                    } else root.message = result.error;
                } catch (error) {
                    root.failed = true;
                    root.message = Translation.tr("Could not read shortcut settings.") + " " + error;
                }
            }
        }
        stderr: StdioCollector { onStreamFinished: { if (text.trim()) console.error("[Shortcuts]", text); } }
        onExited: (exitCode, exitStatus) => {
            if (!receivedResponse && exitCode !== 0) {
                root.failed = true;
                root.message = Translation.tr("Could not start the shortcut editor. Check Python 3 and the terminal logs.");
            }
            if (root.refreshPending) {
                root.refreshPending = false;
                if (!root.failed) refreshTimer.restart();
            }
        }
    }

    SettingsSection {
        icon: "keyboard"
        title: Translation.tr("Shortcuts") + " · " + root.visibleCount
        StyledText {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            text: Translation.tr("Select an action to edit its keys. Linked actions stay together.")
            color: Appearance.colors.colSubtext
        }
        RowLayout {
            Layout.fillWidth: true
            MaterialTextField {
                id: search
                Layout.fillWidth: true
                placeholderText: Translation.tr("Search actions, keys or categories")
            }
            RippleButton {
                implicitWidth: 36; implicitHeight: 36
                Accessible.name: Translation.tr("Refresh")
                enabled: !worker.running
                onClicked: root.request("list")
                contentItem: MaterialSymbol { text: "refresh"; iconSize: 22; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                StyledToolTip { text: Translation.tr("Refresh") }
            }
        }
        Flow {
            Layout.fillWidth: true
            spacing: 8
            RippleButtonWithIcon {
                materialIcon: "description"
                mainText: Translation.tr("Overrides file")
                enabled: root.storeExists
                onClicked: Qt.openUrlExternally("file://" + root.storePath)
                altAction: () => { Quickshell.clipboardText = root.storePath; }
                StyledToolTip { text: root.storePath + "\n" + Translation.tr("Created when you save the first customization. Right-click to copy its path.") }
            }
            RippleButtonWithIcon {
                materialIcon: "folder_open"
                mainText: Translation.tr("Open folder")
                onClicked: Qt.openUrlExternally("file://" + root.storeDirectory)
                altAction: () => { Quickshell.clipboardText = root.storeDirectory; }
                StyledToolTip { text: root.storeDirectory }
            }
        }
        StyledText {
            Layout.fillWidth: true
            visible: root.failed || worker.running
            wrapMode: Text.WordWrap
            text: root.message
            color: root.failed ? Appearance.m3colors.m3error : Appearance.colors.colSubtext
        }
    }

    SettingsSection {
        title: Translation.tr("Categories")
        StyledText {
            visible: !worker.running && root.visibleCount === 0 && !root.failed
            text: Translation.tr("No matching shortcuts.")
        }
        Repeater {
            model: root.groups
            delegate: ColumnLayout {
                id: category
                required property var modelData
                Layout.fillWidth: true
                spacing: 0
                RippleButton {
                    Layout.fillWidth: true
                    implicitHeight: 36
                    horizontalPadding: 4
                    Accessible.name: category.modelData.name
                    onClicked: root.toggleCategory(category.modelData.name)
                    contentItem: RowLayout {
                        spacing: 8
                        MaterialSymbol { text: root.expanded(category.modelData.name) ? "expand_more" : "chevron_right"; iconSize: 20 }
                        StyledText {
                            Layout.fillWidth: true
                            text: Translation.tr(category.modelData.name)
                            font.weight: Font.DemiBold
                        }
                        StyledText { text: category.modelData.entries.length; color: Appearance.colors.colSubtext }
                    }
                }
                Loader {
                    Layout.fillWidth: true
                    active: root.expanded(category.modelData.name)
                    visible: active
                    Layout.preferredHeight: item ? item.implicitHeight : 0
                    sourceComponent: ColumnLayout {
                        spacing: 0
                        Repeater {
                            model: category.modelData.entries
                            delegate: ColumnLayout {
                                id: shortcutRow
                                required property var modelData
                                required property int index
                                Layout.fillWidth: true
                                spacing: 0
                                RippleButton {
                                    id: rowButton
                                    Layout.fillWidth: true
                                    implicitHeight: 38
                                    horizontalPadding: 8
                                    toggled: root.selectedId === shortcutRow.modelData.id
                                    colBackgroundToggled: Appearance.colors.colLayer2
                                    colBackgroundToggledHover: Appearance.colors.colLayer2Hover
                                    enabled: !worker.running
                                    Accessible.name: ShortcutSymbols.description(shortcutRow.modelData) + ": " + shortcutRow.modelData.current
                                    onClicked: root.select(shortcutRow.modelData)
                                    contentItem: RowLayout {
                                        spacing: 8
                                        StyledText {
                                            Layout.fillWidth: true
                                            Layout.minimumWidth: 0
                                            text: ShortcutSymbols.description(shortcutRow.modelData)
                                            font.pixelSize: Appearance.font.pixelSize.small
                                            elide: Text.ElideRight
                                        }
                                        MaterialSymbol {
                                            visible: shortcutRow.modelData.modified
                                            text: "edit_note"
                                            iconSize: 16
                                            color: Appearance.colors.colPrimary
                                        }
                                        MaterialSymbol {
                                            visible: shortcutRow.modelData.count > 1
                                            text: "link"
                                            iconSize: 16
                                            color: Appearance.colors.colSubtext
                                        }
                                        ShortcutKeycaps { combination: shortcutRow.modelData.current }
                                    }
                                    StyledToolTip { text: root.details(shortcutRow.modelData) }
                                }
                                Loader {
                                    Layout.fillWidth: true
                                    active: root.selectedId === shortcutRow.modelData.id
                                    visible: active
                                    Layout.preferredHeight: item ? item.implicitHeight : 0
                                    sourceComponent: editor
                                }
                                Rectangle {
                                    visible: shortcutRow.index < category.modelData.entries.length - 1
                                    Layout.fillWidth: true
                                    implicitHeight: 1
                                    color: Appearance.m3colors.m3outlineVariant
                                    opacity: 0.35
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    Component {
        id: editor
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 8
            RowLayout {
                Layout.topMargin: 8
                StyledText { text: Translation.tr("Default:"); color: Appearance.colors.colSubtext }
                ShortcutKeycaps { combination: root.selectedDefault }
                Item { Layout.fillWidth: true }
            }
            MaterialTextField {
                Layout.fillWidth: true
                text: root.editedCombination
                enabled: !worker.running
                placeholderText: "SUPER + SHIFT + E"
                Component.onCompleted: { forceActiveFocus(); selectAll(); }
                onTextEdited: root.editedCombination = text
                onAccepted: { if (text.trim() && !worker.running) root.request("set", root.selectedId, text); }
            }
            StyledText {
                Layout.fillWidth: true
                text: root.failed ? root.message : Translation.tr("Use + between keys: SUPER + Return, CTRL + F1, SUPER + mouse:272.")
                font.pixelSize: Appearance.font.pixelSize.smaller
                wrapMode: Text.WordWrap
                color: root.failed ? Appearance.m3colors.m3error : Appearance.colors.colSubtext
            }
            Flow {
                Layout.fillWidth: true
                Layout.bottomMargin: 12
                spacing: 8
                DialogButton {
                    buttonText: Translation.tr("Save & apply")
                    enabled: !worker.running && root.editedCombination.trim().length > 0
                    onClicked: root.request("set", root.selectedId, root.editedCombination)
                }
                DialogButton {
                    buttonText: Translation.tr("Restore default")
                    enabled: !worker.running && root.selectedModified
                    onClicked: root.request("reset", root.selectedId)
                }
                DialogButton {
                    buttonText: Translation.tr("Cancel")
                    enabled: !worker.running
                    onClicked: root.selectedId = ""
                }
            }
        }
    }

    SettingsSection {
        icon: "keyboard"
        title: Translation.tr("Shortcut guide appearance")
        RippleButtonWithIcon {
            materialIcon: root.showGuide ? "expand_less" : "expand_more"
            mainText: root.showGuide ? Translation.tr("Hide options") : Translation.tr("Show options")
            onClicked: root.showGuide = !root.showGuide
        }
        ColumnLayout {
            Layout.fillWidth: true
            visible: root.showGuide
            ContentSubsection {
                title: Translation.tr("Super key symbol")
                tooltip: Translation.tr("You can also manually edit cheatsheet.superKey")
                ConfigSelectionArray {
                    currentValue: Config.options.cheatsheet.superKey
                    onSelected: newValue => {
                        Config.options.cheatsheet.superKey = newValue;
                    }
                    // Use a nerdfont to see the icons
                    options: ([
                      "󰖳", "", "󰨡", "", "󰌽", "󰣇", "", "", "",
                      "", "", "󱄛", "", "", "", "⌘", "󰀲", "󰟍", ""
                    ]).map(icon => { return {
                      displayName: icon,
                      value: icon
                      }
                    })
                }
            }

            ConfigSwitch {
                buttonIcon: "󰘵"
                text: Translation.tr("Use macOS-like symbols for mods keys")
                checked: Config.options.cheatsheet.useMacSymbol
                onCheckedChanged: {
                    Config.options.cheatsheet.useMacSymbol = checked;
                }
                StyledToolTip {
                    text: Translation.tr("e.g. 󰘴  for Ctrl, 󰘵  for Alt, 󰘶  for Shift, etc")
                }
            }

            ConfigSwitch {
                buttonIcon: "󱊶"
                text: Translation.tr("Use symbols for function keys")
                checked: Config.options.cheatsheet.useFnSymbol
                onCheckedChanged: {
                    Config.options.cheatsheet.useFnSymbol = checked;
                }
                StyledToolTip {
                  text: Translation.tr("e.g. 󱊫 for F1, 󱊶  for F12")
                }
            }
            ConfigSwitch {
                buttonIcon: "󰍽"
                text: Translation.tr("Use symbols for mouse")
                checked: Config.options.cheatsheet.useMouseSymbol
                onCheckedChanged: {
                    Config.options.cheatsheet.useMouseSymbol = checked;
                }
                StyledToolTip {
                  text: Translation.tr("Replace 󱕐   for \"Scroll ↓\", 󱕑   \"Scroll ↑\", L󰍽   \"LMB\", R󰍽   \"RMB\", 󱕒   \"Scroll ↑/↓\" and ⇞/⇟ for \"Page_↑/↓\"")
                }
            }
            ConfigSwitch {
                buttonIcon: "highlight_keyboard_focus"
                text: Translation.tr("Split buttons")
                checked: Config.options.cheatsheet.splitButtons
                onCheckedChanged: {
                    Config.options.cheatsheet.splitButtons = checked;
                }
                StyledToolTip {
                    text: Translation.tr("Display modifiers and keys in multiple keycap (e.g., \"Ctrl + A\" instead of \"Ctrl A\" or \"󰘴 + A\" instead of \"󰘴 A\")")
                }

            }

            ConfigSpinBox {
                text: Translation.tr("Keybind font size")
                value: Config.options.cheatsheet.fontSize.key
                from: 8
                to: 30
                stepSize: 1
                onValueChanged: {
                    Config.options.cheatsheet.fontSize.key = value;
                }
            }
            ConfigSpinBox {
                text: Translation.tr("Description font size")
                value: Config.options.cheatsheet.fontSize.comment
                from: 8
                to: 30
                stepSize: 1
                onValueChanged: {
                    Config.options.cheatsheet.fontSize.comment = value;
                }
            }
        }
    }
}
