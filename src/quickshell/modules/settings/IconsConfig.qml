pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import QtQuick.Dialogs
import Quickshell
import Quickshell.Widgets
import qs.services
import qs.modules.common
import qs.modules.common.widgets

SettingsPage {
    id: root
    property alias environmentPaths: environmentPaths
    property string selectedTheme: IconTheme.theme
    onSelectedThemeChanged: previewTimer.restart()
    Timer {
        id: previewTimer
        interval: 200
        onTriggered: {
            if (IconTheme.busy) { restart(); return; }
            if (root.selectedTheme) IconTheme.preview(root.selectedTheme);
        }
    }
    property string selectedApplication: ""
    property string query: ""
    readonly property var app: IconTheme.applications.find(a => a.id === selectedApplication)
    readonly property var filteredApps: IconTheme.applications.filter(a => (a.name + " " + a.id).toLowerCase().includes(query.toLowerCase()))
    Connections {
        target: IconTheme
        function onThemeChanged() { root.selectedTheme = IconTheme.theme; }
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
        RowLayout {
            Layout.fillWidth: true
            Repeater {
                model: ["folder", "applications-system", "network-wireless", "user-trash"]
                delegate: IconImage {
                    required property string modelData
                    Layout.alignment: Qt.AlignHCenter
                    implicitSize: 40
                    source: IconTheme.previewTheme === root.selectedTheme ? (IconTheme.previewIcons[modelData] || IconTheme.iconPath("image-missing")) : IconTheme.iconPath(modelData)
                }
            }
        }
        StyledText {
            Layout.fillWidth: true
            text: Translation.tr("Applied: ") + IconTheme.theme
            color: Appearance.colors.colSubtext
            wrapMode: Text.WordWrap
        }
        RowLayout {
            RippleButtonWithIcon {
                materialIcon: "check"
                mainText: Translation.tr("Apply to all environments")
                enabled: !IconTheme.busy && root.selectedTheme.length > 0
                onClicked: IconTheme.apply({theme: root.selectedTheme})
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
            model: root.filteredApps.map(a => ({name: a.name, id: a.id}))
            displayText: currentIndex < 0 ? Translation.tr("Choose an application") : currentText
            textRole: "name"
            currentIndex: root.filteredApps.findIndex(a => a.id === root.selectedApplication)
            onActivated: index => { root.selectedApplication = root.filteredApps[index].id; replacement.text = ""; }
        }
        RowLayout {
            visible: !!root.app
            IconImage { implicitSize: 48; source: root.app ? IconTheme.aliases[root.app.id.replace(/\.desktop$/, "")] || IconTheme.iconPath(root.app.icon) : "" }
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
                onClicked: IconTheme.apply({theme: IconTheme.theme, application: root.selectedApplication, source: replacement.text.trim()})
            }
            RippleButtonWithIcon {
                materialIcon: "undo"
                mainText: Translation.tr("Default")
                enabled: !!root.app && !!IconTheme.overrides[root.app.id] && !IconTheme.busy
                onClicked: IconTheme.apply({theme: IconTheme.theme, application: root.selectedApplication, reset: true})
            }
        }
    }
    EnvironmentPaths { id: environmentPaths }
}
