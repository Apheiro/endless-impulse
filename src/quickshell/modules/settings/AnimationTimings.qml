pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets

ColumnLayout {
    id: root
    Layout.fillWidth: true
    property bool expanded: false
    readonly property var timings: [
        {key: "sidebarOpen", label: Translation.tr("Sidebar opening"), description: Translation.tr("Slide into view from the screen edge."), duration: 600},
        {key: "sidebarClose", label: Translation.tr("Sidebar closing"), description: Translation.tr("Slide out of view toward the screen edge."), duration: 600},
        {key: "move", label: Translation.tr("Notification & widget transitions"), description: Translation.tr("Shared movement timing for notification cards, widget layouts and expanding controls."), duration: 500},
        {key: "smallMove", label: Translation.tr("Switches & tab indicators"), description: Translation.tr("Switch handles, selected-tab indicators and small workspace movements."), duration: 350},
        {key: "enter", label: Translation.tr("Workspace previews & content reveal"), description: Translation.tr("Revealing workspace previews, images and expandable content."), duration: 400},
        {key: "effects", label: Translation.tr("Quick-menu fades & control colors"), description: Translation.tr("Content fades when switching quick menus, plus hover and selection color transitions."), duration: 200},
        {key: "resize", label: Translation.tr("Quick-menu & widget resizing"), description: Translation.tr("The frame resizing between quick menus, tray menus and desktop widgets."), duration: 300},
        {key: "bounce", label: Translation.tr("Quick-toggle button feedback"), description: Translation.tr("The size feedback of grouped buttons, including sidebar quick toggles."), duration: 400},
        {key: "scroll", label: Translation.tr("Scrolling in lists & panels"), description: Translation.tr("The smooth scrolling used by shared list and panel controls."), duration: 200}
    ]
    function compositorLabel(name) {
        const labels = {
            "global": Translation.tr("Compositor default"),
            "windowsIn": Translation.tr("Windows: opening"),
            "windowsOut": Translation.tr("Windows: closing"),
            "windowsMove": Translation.tr("Windows: moving"),
            "fadeIn": Translation.tr("Windows: fade in"),
            "fadeOut": Translation.tr("Windows: fade out"),
            "layersIn": Translation.tr("Other panels: opening"),
            "layersOut": Translation.tr("Other panels: closing"),
            "fadeLayersIn": Translation.tr("Other panels: fade in"),
            "fadeLayersOut": Translation.tr("Other panels: fade out"),
            "workspaces": Translation.tr("Workspace switching"),
            "specialWorkspaceIn": Translation.tr("Special workspace: opening"),
            "specialWorkspaceOut": Translation.tr("Special workspace: closing"),
            "border": Translation.tr("Window border colors"),
            "borderangle": Translation.tr("Window border rotation"),
            "zoomFactor": Translation.tr("Desktop zoom")
        };
        return labels[name] || name;
    }
    RippleButtonWithIcon {
        Layout.fillWidth: true
        materialIcon: root.expanded ? "expand_less" : "tune"
        mainText: Translation.tr("Individual durations")
        onClicked: {
            root.expanded = !root.expanded;
            if (root.expanded) AnimationSpeed.refresh();
        }
    }
    Loader {
        Layout.fillWidth: true
        active: root.expanded
        visible: active
        sourceComponent: ColumnLayout {
            spacing: 16
            StyledText {
                Layout.fillWidth: true
                text: Translation.tr("Base durations before the global speed multiplier. Reset any value using its reset button.")
                wrapMode: Text.WordWrap
                color: Appearance.colors.colSubtext
            }
            StyledText { text: Translation.tr("Interface · shared timings"); font.weight: Font.DemiBold }
            GridLayout {
                Layout.fillWidth: true
                columns: width >= 760 ? 2 : 1
                columnSpacing: 24
                rowSpacing: 16
                Repeater {
                    model: root.timings
                    delegate: AnimationDurationEditor {
                        required property var modelData
                        objectName: "animation-duration-" + modelData.key
                        label: modelData.label
                        description: modelData.description
                        value: Config.options.appearance.animationDurations[modelData.key]
                        defaultValue: modelData.duration
                        onEdited: duration => Config.options.appearance.animationDurations[modelData.key] = duration
                    }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                StyledText { Layout.fillWidth: true; text: Translation.tr("Windows & workspaces (Hyprland)"); font.weight: Font.DemiBold }
                RippleButtonWithIcon { materialIcon: "refresh"; mainText: ""; onClicked: AnimationSpeed.refresh() }
            }
            StyledText {
                Layout.fillWidth: true
                visible: AnimationSpeed.error.length > 0
                text: AnimationSpeed.error
                wrapMode: Text.WordWrap
                color: Appearance.m3colors.m3error
            }
            GridLayout {
                Layout.fillWidth: true
                columns: width >= 760 ? 2 : 1
                columnSpacing: 24
                rowSpacing: 16
                Repeater {
                    model: AnimationSpeed.animations
                    delegate: AnimationDurationEditor {
                        required property var modelData
                        objectName: "compositor-duration-" + modelData.name
                        label: root.compositorLabel(modelData.name) + (modelData.enabled ? "" : " · " + Translation.tr("Disabled"))
                        description: modelData.name
                        enabled: modelData.enabled
                        value: AnimationSpeed.durations[modelData.name] ?? modelData.duration
                        defaultValue: modelData.duration
                        onEdited: duration => AnimationSpeed.setDuration(modelData.name, duration === modelData.duration ? null : duration)
                    }
                }
            }
        }
    }
}
