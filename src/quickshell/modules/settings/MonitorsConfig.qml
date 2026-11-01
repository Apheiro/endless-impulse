pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.settings
import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets

SettingsPage {
    id: root
    property string selectedName: ""
    property string relativeName: ""
    property bool draggingMonitor: false
    interactive: !draggingMonitor
    readonly property var displays: DesktopSettings.monitors.filter(monitor => !monitor.disabled)
    readonly property var selected: displays.find(monitor => monitor.name === selectedName) ?? displays[0] ?? null
    readonly property var selectedSpec: selected ? DesktopSettings.monitor(selected.name) : ({})
    readonly property var bounds: {
        if (!displays.length) return {x: 0, y: 0, width: 1920, height: 1080};
        const rectangles = displays.map(monitor => rectangle(monitor.name));
        const x = Math.min(...rectangles.map(rect => rect.x));
        const y = Math.min(...rectangles.map(rect => rect.y));
        return {x: x, y: y, width: Math.max(...rectangles.map(rect => rect.x + rect.width)) - x,
            height: Math.max(...rectangles.map(rect => rect.y + rect.height)) - y};
    }
    Component.onCompleted: { if (!DesktopSettings.loaded) DesktopSettings.refresh(); }

    function rectangle(name) {
        const spec = DesktopSettings.monitor(name);
        const match = (spec.mode ?? "1920x1080").match(/(\d+)x(\d+)/);
        const rotated = (spec.transform & 1) !== 0;
        return {x: spec.x ?? 0, y: spec.y ?? 0,
            width: Number(match?.[rotated ? 2 : 1] ?? 1920) / (spec.scale ?? 1),
            height: Number(match?.[rotated ? 1 : 2] ?? 1080) / (spec.scale ?? 1)};
    }
    function place(direction) {
        const other = displays.find(monitor => monitor.name === relativeName && monitor.name !== selected.name)
            ?? displays.find(monitor => monitor.name !== selected.name);
        if (!other) return;
        const reference = rectangle(other.name);
        const current = rectangle(selected.name);
        let x = reference.x;
        let y = reference.y;
        if (direction === "left") x -= current.width;
        if (direction === "right") x += reference.width;
        if (direction === "above") y -= current.height;
        if (direction === "below") y += reference.height;
        DesktopSettings.putMonitor(selected.name, {x: Math.round(x), y: Math.round(y)});
    }

    SettingsSection {
        title: Translation.tr("Display arrangement")
        icon: "desktop_windows"
        enabled: DesktopSettings.loaded && !DesktopSettings.busy && !DesktopSettings.transaction
        StyledText {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            text: Translation.tr("Select a display or drag it to change its position in the draft. Coordinates and size account for orientation and scaling. Your layout changes only when you test it.")
        }
        Rectangle {
            id: canvas
            Layout.fillWidth: true
            implicitHeight: 260
            radius: Appearance.rounding.small
            color: Appearance.colors.colLayer1
            clip: true
            readonly property real diagramScale: Math.min((width - 40) / Math.max(1, root.bounds.width), (height - 40) / Math.max(1, root.bounds.height))
            readonly property real offsetX: (width - root.bounds.width * diagramScale) / 2
            readonly property real offsetY: (height - root.bounds.height * diagramScale) / 2
            Repeater {
                model: root.displays
                delegate: Rectangle {
                    id: tile
                    required property var modelData
                    readonly property var rect: root.rectangle(modelData.name)
                    property real offsetX: 0
                    property real offsetY: 0
                    x: canvas.offsetX + (rect.x - root.bounds.x) * canvas.diagramScale
                    y: canvas.offsetY + (rect.y - root.bounds.y) * canvas.diagramScale
                    width: rect.width * canvas.diagramScale
                    height: rect.height * canvas.diagramScale
                    transform: Translate { x: tile.offsetX; y: tile.offsetY }
                    radius: 8
                    color: root.selected?.name === modelData.name ? Appearance.colors.colSecondaryContainer : Appearance.colors.colLayer2
                    border.width: 2
                    border.color: root.selected?.name === modelData.name ? Appearance.colors.colPrimary : Appearance.m3colors.m3outlineVariant
                    StyledText {
                        anchors.fill: parent
                        anchors.margins: 8
                        text: tile.modelData.name + "\n" + Math.round(tile.rect.width) + " × " + Math.round(tile.rect.height)
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        wrapMode: Text.WordWrap
                        elide: Text.ElideRight
                    }
                    MouseArea {
                        anchors.fill: parent
                        preventStealing: true
                        cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                        property point start
                        onPressed: mouse => {
                            root.draggingMonitor = true;
                            root.selectedName = tile.modelData.name;
                            start = mapToItem(canvas, mouse.x, mouse.y);
                        }
                        onPositionChanged: mouse => {
                            if (!pressed) return;
                            const point = mapToItem(canvas, mouse.x, mouse.y);
                            tile.offsetX = point.x - start.x;
                            tile.offsetY = point.y - start.y;
                        }
                        onReleased: {
                            if (Math.abs(tile.offsetX) + Math.abs(tile.offsetY) > 3) {
                                DesktopSettings.putMonitor(tile.modelData.name, {
                                    x: Math.round(tile.rect.x + tile.offsetX / canvas.diagramScale),
                                    y: Math.round(tile.rect.y + tile.offsetY / canvas.diagramScale)});
                            }
                            tile.offsetX = 0;
                            tile.offsetY = 0;
                            root.draggingMonitor = false;
                        }
                        onCanceled: {
                            tile.offsetX = 0;
                            tile.offsetY = 0;
                            root.draggingMonitor = false;
                        }
                    }
                }
            }
            StyledText {
                anchors.centerIn: parent
                visible: !root.displays.length
                text: DesktopSettings.busy ? Translation.tr("Loading displays…") : Translation.tr("No connected displays found.")
            }
        }
    }
    SettingsSection {
        visible: !!root.selected
        enabled: DesktopSettings.loaded && !DesktopSettings.busy && !DesktopSettings.transaction
        title: root.selected ? root.selected.name + " · " + root.selected.description : ""
        icon: "monitor"
        StyledComboBox {
            model: root.displays.map(monitor => monitor.name)
            currentIndex: Math.max(0, root.displays.findIndex(monitor => monitor.name === root.selected?.name))
            onActivated: index => root.selectedName = root.displays[index].name
        }
        ContentSubsection {
            title: Translation.tr("Resolution and refresh rate")
            StyledComboBox {
                property var modes: [...new Set([root.selectedSpec.mode, ...(root.selected?.availableModes ?? [])])].filter(mode => !!mode)
                model: modes
                currentIndex: Math.max(0, modes.indexOf(root.selectedSpec.mode))
                onActivated: index => DesktopSettings.putMonitor(root.selected.name, {mode: modes[index]})
            }
        }
        DesktopSettingField {
            field: ({type: "enum", label: "Orientation", choices: ["Normal", "90°", "180°", "270°", "Flipped", "Flipped 90°", "Flipped 180°", "Flipped 270°"]})
            value: field.choices[root.selectedSpec.transform ?? 0]
            onEdited: value => DesktopSettings.putMonitor(root.selected.name, {transform: field.choices.indexOf(value)})
        }
        DesktopSettingField {
            field: ({type: "int", label: "Scale (%)", minimum: 50, maximum: 400, default: 100})
            value: Math.round((root.selectedSpec.scale ?? 1) * 100)
            onEdited: value => DesktopSettings.putMonitor(root.selected.name, {scale: value / 100})
        }
        DesktopSettingField {
            field: ({type: "int", label: "Position X (logical pixels)", minimum: -1000000, maximum: 1000000, default: 0})
            value: root.selectedSpec.x ?? 0
            onEdited: value => DesktopSettings.putMonitor(root.selected.name, {x: value})
        }
        DesktopSettingField {
            field: ({type: "int", label: "Position Y (logical pixels)", minimum: -1000000, maximum: 1000000, default: 0})
            value: root.selectedSpec.y ?? 0
            onEdited: value => DesktopSettings.putMonitor(root.selected.name, {y: value})
        }
        ContentSubsection {
            visible: root.displays.length > 1
            title: Translation.tr("Place relative to another display")
            StyledComboBox {
                property var others: root.displays.filter(monitor => monitor.name !== root.selected?.name)
                model: others.map(monitor => monitor.name)
                onActivated: index => root.relativeName = others[index].name
            }
            Flow {
                Layout.fillWidth: true
                spacing: 8
                Repeater {
                    model: ["left", "right", "above", "below"]
                    RippleButtonWithIcon {
                        required property string modelData
                        mainText: Translation.tr(modelData.charAt(0).toUpperCase() + modelData.slice(1))
                        materialIcon: modelData === "left" ? "arrow_back" : modelData === "right" ? "arrow_forward" : modelData === "above" ? "arrow_upward" : "arrow_downward"
                        onClicked: root.place(modelData)
                    }
                }
            }
        }
        RippleButtonWithIcon {
            visible: !!root.selected && Object.prototype.hasOwnProperty.call(DesktopSettings.saved.monitors, root.selected.name)
            materialIcon: "restore"
            mainText: Translation.tr("Remove saved overrides for this display")
            onClicked: DesktopSettings.put("monitors", root.selected.name, null)
        }
    }
}
