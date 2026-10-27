//@ pragma UseQApplication
//@ pragma Env QS_NO_RELOAD_POPUP=1
//@ pragma Env QT_QUICK_CONTROLS_STYLE=Basic
//@ pragma Env QT_QUICK_FLICKABLE_WHEEL_DECELERATION=10000

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import Quickshell
import Quickshell.Wayland
import Quickshell.Hyprland
import qs.services
import qs.modules.common
import qs.modules.common.widgets
import qs.modules.common.functions as CF
import "modules/settings" as Settings

PanelWindow {
    id: root
    property int currentPage: 0
    readonly property var pages: catalog.pages
    readonly property var selectedPage: pages[currentPage]
    readonly property int matchingPages: pages.filter((page, index) => catalog.matches(index, navigationSearch.text)).length
    property string openingMonitorName: ""
    property bool opened: false
    property bool allowShowing: true

    visible: opened && allowShowing
    implicitWidth: 900
    implicitHeight: 600
    exclusiveZone: 0
    color: "transparent"
    WlrLayershell.namespace: "quickshell:settings"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.OnDemand

    function sizeForScreen(screenWidth, screenHeight, reserved) {
        return Qt.size(
            Math.round(Math.max(1, screenWidth - (reserved[0] ?? 0) - (reserved[2] ?? 0)) * 0.8),
            Math.round(Math.max(1, screenHeight - (reserved[1] ?? 0) - (reserved[3] ?? 0)) * 0.8));
    }

    function finishOpening() {
        if (opened) return;
        // Focus information arrives asynchronously. Resolve it immediately before mapping,
        // rather than capturing the default output during component construction.
        const focused = HyprlandData.monitors.find(monitor => monitor.focused);
        const focusedName = focused?.name ?? Hyprland.focusedMonitor?.name;
        const selectedScreen = Quickshell.screens.find(screen => screen.name === focusedName);
        if (selectedScreen) root.screen = selectedScreen;
        openingMonitorName = root.screen.name;
        const monitor = HyprlandData.monitors.find(monitor => monitor.name === openingMonitorName);
        const size = sizeForScreen(root.screen.width, root.screen.height, monitor?.reserved ?? []);
        implicitWidth = size.width;
        implicitHeight = size.height;
        opened = true;
        openingTimeout.stop();
    }

    Settings.SettingsCatalog { id: catalog }

    Component.onCompleted: {
        if (HyprlandData.monitors.some(monitor => monitor.focused)) finishOpening();
        else openingTimeout.start();
        MaterialThemeLoader.reapplyTheme();
        Config.readWriteDelay = 0;
    }

    Connections {
        target: HyprlandData
        function onMonitorsChanged() {
            if (!root.opened && HyprlandData.monitors.some(monitor => monitor.focused)) root.finishOpening();
        }
    }

    Timer {
        id: openingTimeout
        interval: 1500
        onTriggered: root.finishOpening()
    }

    Rectangle {
        anchors.fill: parent
        radius: Appearance.rounding.large
        color: Appearance.m3colors.m3background
    }

    function movePage(offset) {
        const indices = pages.map((page, index) => index).filter(index => catalog.matches(index, navigationSearch.text));
        if (indices.length === 0) return;
        const position = indices.indexOf(currentPage);
        currentPage = indices[(position + offset + indices.length) % indices.length];
    }

    Shortcut { sequence: "Ctrl+f"; onActivated: { navigationSearch.forceActiveFocus(); navigationSearch.selectAll(); } }
    Shortcut { sequence: "Ctrl+w"; onActivated: Qt.quit() }
    Shortcut { sequences: ["Ctrl+Tab", "Ctrl+PgDown"]; onActivated: root.movePage(1) }
    Shortcut { sequences: ["Ctrl+Shift+Tab", "Ctrl+PgUp"]; onActivated: root.movePage(-1) }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 12

        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 10
            StyledText {
                Layout.fillWidth: true
                text: Translation.tr("Settings")
                font.pixelSize: Appearance.font.pixelSize.larger
                font.weight: Font.Medium
            }
            RippleButton {
                implicitWidth: 34
                implicitHeight: 34
                buttonRadius: Appearance.rounding.full
                Accessible.name: Translation.tr("Close")
                onClicked: Qt.quit()
                contentItem: MaterialSymbol {
                    text: "close"
                    iconSize: 20
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 12

            ColumnLayout {
                Layout.preferredWidth: root.width < 1050 ? 210 : 230
                Layout.minimumWidth: Layout.preferredWidth
                Layout.maximumWidth: Layout.preferredWidth
                Layout.fillHeight: true
                spacing: 12

                MaterialTextField {
                    id: navigationSearch
                    Layout.fillWidth: true
                    placeholderText: Translation.tr("Find a category…")
                    Accessible.name: Translation.tr("Find a settings category")
                    wrapMode: TextInput.NoWrap
                    selectByMouse: true
                    Keys.onEscapePressed: clear()
                    Keys.onReturnPressed: {
                        for (let i = 0; i < root.pages.length; i++) {
                            if (catalog.matches(i, text)) { root.currentPage = i; break; }
                        }
                    }
                }

                ScrollView {
                    id: navigationScroll
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    contentWidth: availableWidth
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                    ColumnLayout {
                        width: navigationScroll.availableWidth
                        spacing: 3
                        Repeater {
                            model: root.pages
                            delegate: ColumnLayout {
                                id: navigationEntry
                                required property int index
                                required property var modelData
                                readonly property bool firstInGroup: {
                                    for (let i = index - 1; i >= 0; i--) {
                                        if (catalog.matches(i, navigationSearch.text)) return root.pages[i].group !== modelData.group;
                                    }
                                    return true;
                                }
                                visible: catalog.matches(index, navigationSearch.text)
                                Layout.fillWidth: true
                                spacing: 4

                                StyledText {
                                    visible: navigationEntry.firstInGroup
                                    Layout.fillWidth: true
                                    Layout.leftMargin: 12
                                    Layout.topMargin: navigationEntry.index === 0 ? 4 : 16
                                    Layout.bottomMargin: 4
                                    text: navigationEntry.modelData.group
                                    font.pixelSize: Appearance.font.pixelSize.smaller
                                    font.weight: Font.DemiBold
                                    color: Appearance.m3colors.m3onSurfaceVariant
                                }

                                RippleButton {
                                    id: navigationButton
                                    Layout.fillWidth: true
                                    implicitHeight: 42
                                    horizontalPadding: 12
                                    toggled: root.currentPage === navigationEntry.index
                                    colBackgroundToggled: Appearance.colors.colSecondaryContainer
                                    colBackgroundToggledHover: Appearance.colors.colSecondaryContainerHover
                                    Accessible.name: navigationEntry.modelData.name
                                    Accessible.role: Accessible.PageTab
                                    Accessible.selected: toggled
                                    onClicked: root.currentPage = navigationEntry.index
                                    contentItem: RowLayout {
                                        spacing: 10
                                        MaterialSymbol {
                                            text: navigationEntry.modelData.icon
                                            iconSize: 21
                                            color: navigationButton.toggled ? Appearance.m3colors.m3onSecondaryContainer : Appearance.colors.colOnLayer0
                                        }
                                        StyledText {
                                            Layout.fillWidth: true
                                            text: navigationEntry.modelData.name
                                            elide: Text.ElideRight
                                            font.pixelSize: Appearance.font.pixelSize.small
                                            font.weight: navigationButton.toggled ? Font.DemiBold : Font.Normal
                                            color: navigationButton.toggled ? Appearance.m3colors.m3onSecondaryContainer : Appearance.colors.colOnLayer0
                                        }
                                    }
                                    StyledToolTip { text: navigationEntry.modelData.description }
                                }
                            }
                        }
                        StyledText {
                            visible: root.matchingPages === 0
                            Layout.fillWidth: true
                            Layout.margins: 12
                            text: Translation.tr("No matching categories. Try another term.")
                            wrapMode: Text.WordWrap
                            color: Appearance.m3colors.m3onSurfaceVariant
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: 1
                    color: Appearance.m3colors.m3outlineVariant
                }
                RippleButtonWithIcon {
                    Layout.fillWidth: true
                    materialIcon: "data_object"
                    mainText: Translation.tr("Open config file")
                    onClicked: Qt.openUrlExternally("file://" + Directories.shellConfigPath)
                    altAction: () => { Quickshell.clipboardText = CF.FileUtils.trimFileProtocol(Directories.shellConfigPath); }
                    StyledToolTip { text: Translation.tr("Open config.json. Right-click to copy its path.") }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: Appearance.rounding.large
                color: Appearance.m3colors.m3surfaceContainerLow

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0
                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.margins: 24
                        spacing: 6
                        StyledText {
                            Layout.fillWidth: true
                            text: root.selectedPage.group
                            font.pixelSize: Appearance.font.pixelSize.small
                            color: Appearance.colors.colPrimary
                        }
                        StyledText {
                            Layout.fillWidth: true
                            text: root.selectedPage.name
                            font.pixelSize: Appearance.font.pixelSize.title
                            font.weight: Font.DemiBold
                            wrapMode: Text.WordWrap
                        }
                        StyledText {
                            Layout.fillWidth: true
                            text: root.selectedPage.description
                            font.pixelSize: Appearance.font.pixelSize.small
                            color: Appearance.m3colors.m3onSurfaceVariant
                            wrapMode: Text.WordWrap
                        }
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: 1
                        color: Appearance.m3colors.m3outlineVariant
                    }
                    Loader {
                        id: pageLoader
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        active: Config.ready
                        source: "modules/settings/" + root.selectedPage.component
                        onLoaded: pageEntrance.restart()
                        NumberAnimation {
                            id: pageEntrance
                            target: pageLoader
                            property: "opacity"
                            from: 0
                            to: 1
                            duration: 140
                            easing.type: Easing.OutCubic
                        }
                    }
                    StyledText {
                        visible: pageLoader.status === Loader.Error
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.margins: 24
                        text: Translation.tr("This page could not be loaded. Check the settings log for details.")
                        wrapMode: Text.WordWrap
                    }
                }
            }
        }
    }
}
