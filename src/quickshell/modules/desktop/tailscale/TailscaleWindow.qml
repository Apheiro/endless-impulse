pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Wayland
import qs.services
import qs.modules.shared
import qs.modules.shared.primitives.common
import qs.modules.shared.widgets

PanelWindow {
    id: window
    screen: Quickshell.screens.find(screen => screen.name === TailscaleControl.screenName) ?? Quickshell.screens[0]
    implicitWidth: Math.min(1050, screen.width * .85) + 2 * Appearance.sizes.elevationMargin
    implicitHeight: Math.min(screen.height * .85, Math.max(430, mainColumn.implicitHeight + 40)) + 2 * Appearance.sizes.elevationMargin
    exclusiveZone: 0
    color: "transparent"
    WlrLayershell.namespace: "quickshell:tailscale"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.OnDemand
    property int tab: 0
    mask: Region { item: surface }
    PanelSurfaceShadow { target: surface }
    // This management window outlives the sidebar/menu that launched it.
    // Global menu focus changes must not dismiss it or interrupt its forms.
    PanelSurface {
        id: surface
        objectName: "tailscaleSurface"
        anchors.fill: parent
        anchors.margins: Appearance.sizes.elevationMargin
        radius: Appearance.rounding.windowRounding
        focus: true
        Keys.onEscapePressed: TailscaleControl.close()
        ColumnLayout {
            id: mainColumn
            anchors.fill: parent
            anchors.margins: 20
            spacing: 12
            RowLayout {
                Layout.fillWidth: true
                Rectangle {
                    implicitWidth: 44; implicitHeight: 44
                    radius: Appearance.rounding.small
                    color: Appearance.colors.colSecondaryContainer
                    CustomIcon { anchors.centerIn: parent; source: "tailscale-symbolic.svg"; width: 25; height: 25; colorize: true; color: Appearance.colors.colOnSecondaryContainer }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    StyledText { Layout.fillWidth: true; elide: Text.ElideRight; text: "Tailscale"; font.pixelSize: Appearance.font.pixelSize.larger; font.weight: Font.DemiBold }
                    StyledText {
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                        text: !TailscaleControl.loaded ? Translation.tr("Loading…")
                            : TailscaleControl.state.running ? TailscaleControl.state.tailnet : Translation.tr("Disconnected")
                        color: Appearance.colors.colSubtext
                        font.pixelSize: Appearance.font.pixelSize.smaller
                    }
                }
                TailscaleBadge { visible: surface.width >= 650; text: TailscaleControl.busy ? Translation.tr("Working…") : TailscaleControl.state.running ? Translation.tr("Connected") : Translation.tr("Disconnected"); icon: TailscaleControl.busy ? "sync" : TailscaleControl.state.running ? "verified_user" : "link_off"; highlighted: TailscaleControl.state.running }
                RippleButtonWithIcon { materialIcon: "admin_panel_settings"; mainText: surface.width >= 650 ? Translation.tr("Administration") : ""; onClicked: TailscaleControl.openURL("https://login.tailscale.com/admin"); Accessible.name: Translation.tr("Open Tailscale administration") }
                RippleButtonWithIcon { mainText: ""; materialIcon: "refresh"; enabled: !TailscaleControl.refreshing; onClicked: TailscaleControl.refresh(); Accessible.name: Translation.tr("Refresh") }
                RippleButtonWithIcon { mainText: ""; materialIcon: "close"; onClicked: TailscaleControl.close(); Accessible.name: Translation.tr("Close") }
            }
            SegmentedControl {
                Layout.fillWidth: true
                currentIndex: window.tab
                model: [{name:Translation.tr("Connections"),icon:"vpn_lock"},
                    {name:Translation.tr("Devices"),icon:"devices"},
                    {name:Translation.tr("Preferences"),icon:"tune"},
                    {name:Translation.tr("Advanced"),icon:"settings"}]
                onActivated: index => window.tab = index
            }
            RowLayout {
                visible: TailscaleControl.error.length > 0
                Layout.fillWidth: true
                MaterialSymbol { text: "error_outline"; iconSize: 21; color: Appearance.colors.colError }
                StyledText { Layout.fillWidth: true; text: TailscaleControl.error; textFormat: Text.PlainText; wrapMode: Text.WordWrap; color: Appearance.colors.colError }
            }
            StyledFlickable {
                Layout.fillWidth: true; Layout.fillHeight: true
                Layout.preferredHeight: page.implicitHeight
                Layout.minimumHeight: 0
                contentWidth: width; contentHeight: page.implicitHeight
                clip: true
                Loader {
                    id: page
                    width: parent.width
                    sourceComponent: window.tab === 0 ? connections : window.tab === 1 ? devices : window.tab === 2 ? preferences : advanced
                }
            }
            RowLayout {
                Layout.fillWidth: true
                visible: TailscaleControl.busy || TailscaleControl.output.length > 0
                StyledText { Layout.fillWidth: true; text: TailscaleControl.busy ? Translation.tr("Operation in progress…") : Translation.tr("Operation output"); color: Appearance.colors.colSubtext }
                RippleButtonWithIcon { visible: TailscaleControl.busy; materialIcon: "stop"; mainText: Translation.tr("Stop"); onClicked: TailscaleControl.request("cancel") }
            }
            RowLayout {
                visible: TailscaleControl.busy
                Layout.fillWidth: true
                MaterialTextField { id: response; Layout.fillWidth: true; placeholderText: Translation.tr("Response to operation prompt"); wrapMode: TextInput.NoWrap; echoMode: TextInput.Password }
                RippleButtonWithIcon { materialIcon: "send"; mainText: Translation.tr("Send response"); enabled: response.text.length > 0; onClicked: { TailscaleControl.request("input", {text: response.text}); response.clear(); } }
            }
            StyledFlickable {
                Layout.fillWidth: true; Layout.preferredHeight: Math.min(150, output.implicitHeight + 16)
                visible: TailscaleControl.output.length > 0
                contentWidth: width; contentHeight: output.implicitHeight
                clip: true
                StyledTextArea {
                    id: output; width: parent.width; readOnly: true; selectByMouse: true
                    text: TailscaleControl.output; wrapMode: TextEdit.Wrap
                    font.family: Appearance.font.family.numbers
                    font.pixelSize: Appearance.font.pixelSize.smaller
                }
            }
        }
    }
    Component { id: connections; TailscaleConnections {} }
    Component { id: devices; TailscaleDevices {} }
    Component { id: preferences; TailscalePreferences {} }
    Component { id: advanced; TailscaleCommandBrowser {} }
}
