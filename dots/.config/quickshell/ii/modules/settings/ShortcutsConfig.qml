import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland
import qs.services
import qs.modules.common
import qs.modules.common.widgets

SettingsPage {
    id: root
    forceWidth: true
    property var shortcuts: []
    property string message: ""
    property bool failed: false
    property bool refreshPending: false
    property string selectedId: ""
    property string selectedDescription: ""
    property string selectedDefault: ""
    property bool selectedModified: false
    property string helperPath: Quickshell.shellPath("scripts/hyprland/shortcuts.py")
    property var filteredShortcuts: shortcuts.filter(entry => {
        const query = search.text.toLowerCase().trim();
        return `${entry.description} ${entry.current} ${entry.default} ${entry.submap}`.toLowerCase().includes(query);
    })

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
    Timer {
        id: refreshTimer
        interval: 200
        onTriggered: root.request("list")
    }
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
                        root.message = Translation.tr("Shortcuts are up to date.");
                        const selected = result.shortcuts.find(entry => entry.id === root.selectedId);
                        if (selected) {
                            combination.text = selected.current;
                            root.selectedModified = selected.modified;
                        } else root.selectedId = "";
                    } else root.message = result.error;
                } catch (error) {
                    root.failed = true;
                    root.message = Translation.tr("Could not read shortcut settings.") + " " + error;
                }
            }
        }
        stderr: StdioCollector {
            onStreamFinished: { if (text.trim()) console.error("[Shortcuts]", text); }
        }
        onExited: (exitCode, exitStatus) => {
            if (!receivedResponse && exitCode !== 0) {
                root.failed = true;
                root.message = Translation.tr("Could not start the shortcut editor. Check Python 3 and the terminal logs.");
            }
            if (root.refreshPending) {
                root.refreshPending = false;
                // Preserve apply errors instead of replacing them with a successful refresh.
                if (!root.failed) refreshTimer.restart();
            }
        }
    }

    SettingsSection {
        icon: "keyboard"
        title: Translation.tr("Shortcuts")
        StyledText {
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            text: Translation.tr("Edit Hyprland shortcuts, including window controls, apps and shell actions. Changes apply when saved. Actions sharing a shortcut move together.")
        }
        RowLayout {
            Layout.fillWidth: true
            MaterialTextField {
                id: search
                Layout.fillWidth: true
                placeholderText: Translation.tr("Search actions or shortcuts")
            }
            DialogButton {
                buttonText: Translation.tr("Refresh")
                enabled: !worker.running
                onClicked: root.request("list")
            }
        }
        StyledText {
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            text: root.message
            color: root.failed ? Appearance.m3colors.m3error : Appearance.colors.colSubtext
        }
    }

    SettingsSection {
        visible: root.selectedId !== ""
        icon: "edit"
        title: Translation.tr("Edit shortcut")
        StyledText {
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            text: root.selectedDescription
        }
        StyledText {
            text: Translation.tr("Default:") + " " + root.selectedDefault
        }
        MaterialTextField {
            id: combination
            Layout.fillWidth: true
            enabled: !worker.running
            placeholderText: "SUPER + SHIFT + E"
            onAccepted: { if (text.trim() && !worker.running) root.request("set", root.selectedId, text); }
        }
        StyledText {
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            text: Translation.tr("Type modifiers and a key, separated by +. Examples: SUPER + Return, CTRL + ALT + F1, XF86AudioMute, SUPER + mouse:272.")
            color: Appearance.colors.colSubtext
        }
        RowLayout {
            DialogButton {
                buttonText: Translation.tr("Save & apply")
                enabled: !worker.running && combination.text.trim().length > 0
                onClicked: root.request("set", root.selectedId, combination.text)
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

    SettingsSection {
        title: Translation.tr("Available shortcuts") + " (" + root.filteredShortcuts.length + ")"
        StyledText {
            visible: !worker.running && root.filteredShortcuts.length === 0 && !root.failed
            text: Translation.tr("No matching shortcuts.")
        }
        Repeater {
            model: root.filteredShortcuts
            delegate: ColumnLayout {
                required property var modelData
                Layout.fillWidth: true
                spacing: 4
                RowLayout {
                    Layout.fillWidth: true
                    StyledText {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        text: modelData.description || Translation.tr("Shortcut") + ": " + modelData.default
                    }
                    DialogButton {
                        buttonText: Translation.tr("Edit")
                        enabled: !worker.running
                        onClicked: {
                            root.selectedId = modelData.id;
                            root.selectedDescription = modelData.description || modelData.default;
                            root.selectedDefault = modelData.default;
                            root.selectedModified = modelData.modified;
                            combination.text = modelData.current;
                            root.contentY = 0;
                            combination.forceActiveFocus();
                        }
                    }
                }
                StyledText {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    text: modelData.current
                        + (modelData.modified ? " · " + Translation.tr("Customized") : "")
                        + (modelData.submap ? " · " + modelData.submap : "")
                        + (modelData.count > 1 ? " · " + modelData.count + " " + Translation.tr("linked actions") : "")
                    color: Appearance.colors.colSubtext
                }
                Item { implicitHeight: 10 }
            }
        }
    }

    SettingsSection {
        icon: "keyboard"
        title: Translation.tr("Cheat sheet")

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
