pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import QtQuick.Dialogs
import Quickshell
import Quickshell.Widgets
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets

SettingsPage {
    id: root
    property alias environmentPaths: environmentPaths
    property string selectedTheme: IconTheme.theme
    property var selectedFallbacks: [...IconTheme.fallbacks]
    readonly property string previewKey: JSON.stringify([selectedTheme, selectedFallbacks])
    readonly property var availableFallbacks: IconTheme.backupThemes.filter(theme => theme.id !== selectedTheme
                                                                               && theme.id !== "hicolor" &&
                                                                               !selectedFallbacks.includes(
                                                                                   theme.id))
    onSelectedThemeChanged: {
        selectedFallbacks = selectedFallbacks.filter(theme => theme !== selectedTheme);
        previewTimer.restart();
    }
    onSelectedFallbacksChanged: previewTimer.restart()
    function moveFallback(index, delta) {
        const next = [...selectedFallbacks];
        const target = index + delta;
        if (target < 0 || target >= next.length)
            return;
        [next[index], next[target]] = [next[target], next[index]];
        selectedFallbacks = next;
    }
    function addFallback(theme) {
        if (theme && theme !== selectedTheme && !selectedFallbacks.includes(theme))
            selectedFallbacks = [...selectedFallbacks, theme];
    }
    Timer {
        id: previewTimer
        interval: 200
        onTriggered: {
            if (IconTheme.busy) {
                restart();
                return;
            }
            if (root.selectedTheme)
                IconTheme.preview(root.selectedTheme, root.selectedFallbacks);
        }
    }
    property string selectedApplication: ""
    property string query: ""
    readonly property var app: IconTheme.applications.find(a => a.id === selectedApplication)
    readonly property var filteredApps: IconTheme.applications.filter(a => (a.name + " " + a.id).toLowerCase(
                                            ).includes(query.toLowerCase()))
    Connections {
        target: IconTheme
        function onThemeChanged() {
            root.selectedTheme = IconTheme.theme;
        }
        function onFallbacksChanged() {
            root.selectedFallbacks = [...IconTheme.fallbacks];
        }
    }
    FileDialog {
        id: iconFile
        title: Translation.tr("Choose an application icon")
        options: FileDialog.DontUseNativeDialog
        nameFilters: [Translation.tr("Icons (*.png *.svg *.xpm)")]
        onAccepted: replacement.text = decodeURIComponent(selectedFile.toString().replace(/^file:\/\//, ""))
    }
    SettingsSection {
        title: Translation.tr("System icons")
        icon: "interests"
        StyledComboBox {
            model: IconTheme.themes
            textRole: "name"
            currentIndex: IconTheme.themes.findIndex(t => t.id === root.selectedTheme)
            onActivated: index => root.selectedTheme = IconTheme.themes[index].id
        }
        StyledText {
            text: Translation.tr("Backup themes")
            font.weight: Font.Medium
        }
        StyledText {
            Layout.fillWidth: true
            text: Translation.tr(
                      "Missing icons are searched in these themes, in order. Each theme keeps its own inherited icons; hicolor is the final fallback.")
            wrapMode: Text.WordWrap
            color: Appearance.colors.colSubtext
            font.pixelSize: Appearance.font.pixelSize.smaller
        }
        Repeater {
            model: root.selectedFallbacks
            delegate: RowLayout {
                id: backupRow
                required property string modelData
                required property int index
                Layout.fillWidth: true
                StyledText {
                    text: (backupRow.index + 1) + "."
                    color: Appearance.colors.colSubtext
                }
                StyledText {
                    Layout.fillWidth: true
                    text: IconTheme.backupThemes.find(theme => theme.id === backupRow.modelData)?.name
                          || backupRow.modelData + " · " + Translation.tr("Not installed")
                    elide: Text.ElideRight
                }
                RippleButtonWithIcon {
                    materialIcon: "arrow_upward"
                    mainText: ""
                    enabled: backupRow.index > 0
                    onClicked: root.moveFallback(backupRow.index, -1)
                }
                RippleButtonWithIcon {
                    materialIcon: "arrow_downward"
                    mainText: ""
                    enabled: backupRow.index < root.selectedFallbacks.length - 1
                    onClicked: root.moveFallback(backupRow.index, 1)
                }
                RippleButtonWithIcon {
                    materialIcon: "close"
                    mainText: ""
                    onClicked: root.selectedFallbacks = root.selectedFallbacks.filter((theme, index) => index
                                                                                                        !== backupRow.index)
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            StyledComboBox {
                id: backupPicker
                model: root.availableFallbacks
                textRole: "name"
                displayText: currentIndex < 0 ? Translation.tr("Choose a backup theme") : currentText
            }
            RippleButtonWithIcon {
                materialIcon: "add"
                mainText: Translation.tr("Add")
                enabled: backupPicker.currentIndex >= 0
                onClicked: root.addFallback(root.availableFallbacks[backupPicker.currentIndex].id)
            }
            RippleButtonWithIcon {
                materialIcon: "auto_fix_high"
                mainText: Translation.tr("Recommended")
                onClicked: {
                    for (const theme of ["breeze", "Adwaita"])
                        if (IconTheme.backupThemes.some(item => item.id === theme))
                            root.addFallback(theme);
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Repeater {
                model: ["folder", "applications-system", "network-wireless", "user-trash"]
                delegate: IconImage {
                    required property string modelData
                    Layout.alignment: Qt.AlignHCenter
                    implicitSize: 40
                    source: IconTheme.previewKey === root.previewKey ? (IconTheme.previewIcons[modelData]
                                                                        || IconTheme.iconPath(
                                                                            "image-missing")) :
                                                                       IconTheme.iconPath(modelData)
                }
            }
        }
        StyledText {
            Layout.fillWidth: true
            text: Translation.tr("Applied: ") + [IconTheme.theme, ...IconTheme.fallbacks, "hicolor"].filter((theme,
                                                                                                             index, list)
                                                                                                            => theme
                                                                                                               && list.indexOf(
                                                                                                                   theme)
                                                                                                               === index).join(
                      " → ")
            color: Appearance.colors.colSubtext
            wrapMode: Text.WordWrap
        }
        RowLayout {
            RippleButtonWithIcon {
                materialIcon: "check"
                mainText: Translation.tr("Apply to all environments")
                enabled: !IconTheme.busy && root.selectedTheme.length > 0
                onClicked: IconTheme.apply({
                                               theme: root.selectedTheme,
                                               fallbacks: root.selectedFallbacks
                                           })
            }
            RippleButtonWithIcon {
                materialIcon: "refresh"
                mainText: Translation.tr("Refresh")
                enabled: !IconTheme.busy
                onClicked: IconTheme.refresh()
            }
        }
        StyledText {
            Layout.fillWidth: true
            visible: IconTheme.busy || IconTheme.message.length > 0
            text: IconTheme.busy ? Translation.tr("Reading icon themes…") : IconTheme.message
            color: IconTheme.failed ? Appearance.m3colors.m3error : Appearance.colors.colSubtext
            wrapMode: Text.WordWrap
        }
    }
    SettingsSection {
        title: Translation.tr("Application overrides")
        icon: "apps"
        MaterialTextField {
            Layout.fillWidth: true
            placeholderText: Translation.tr("Search applications…")
            onTextChanged: root.query = text
        }
        StyledComboBox {
            model: root.filteredApps.map(a => ({
                name: a.name,
                id: a.id
            }))
            displayText: currentIndex < 0 ? Translation.tr("Choose an application") : currentText
            textRole: "name"
            currentIndex: root.filteredApps.findIndex(a => a.id === root.selectedApplication)
            onActivated: index => {
                root.selectedApplication = root.filteredApps[index].id;
                replacement.text = "";
            }
        }
        RowLayout {
            visible: !!root.app
            IconImage {
                implicitSize: 48
                source: root.app ? IconTheme.aliases[root.app.id.replace(/\.desktop$/, "")]
                                   || IconTheme.iconPath(root.app.icon) : ""
            }
            StyledText {
                Layout.fillWidth: true
                text: root.app ? root.app.name + "\n" + root.app.icon : ""
                wrapMode: Text.WrapAnywhere
            }
        }
        MaterialTextField {
            id: replacement
            Layout.fillWidth: true
            enabled: !!root.app
            placeholderText: Translation.tr("Theme icon name or image path")
        }
        RowLayout {
            RippleButtonWithIcon {
                materialIcon: "folder_open"
                mainText: Translation.tr("Choose image")
                enabled: !!root.app && !IconTheme.busy
                onClicked: iconFile.open()
            }
            RippleButtonWithIcon {
                materialIcon: "save"
                mainText: Translation.tr("Save")
                enabled: !!root.app && replacement.text.trim().length > 0 && !IconTheme.busy
                onClicked: IconTheme.apply({
                                               theme: IconTheme.theme,
                                               application: root.selectedApplication,
                                               source: replacement.text.trim()
                                           })
            }
            RippleButtonWithIcon {
                materialIcon: "undo"
                mainText: Translation.tr("Default")
                enabled: !!root.app && !!IconTheme.overrides[root.app.id] && !IconTheme.busy
                onClicked: IconTheme.apply({
                                               theme: IconTheme.theme,
                                               application: root.selectedApplication,
                                               reset: true
                                           })
            }
        }
    }
    EnvironmentPaths {
        id: environmentPaths
    }
}
