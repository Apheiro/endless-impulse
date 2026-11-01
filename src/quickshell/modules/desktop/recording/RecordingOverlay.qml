pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Shapes
import Quickshell
import Quickshell.Wayland
import qs.services
import qs.modules.shared

Scope {
    Variants {
        model: Quickshell.screens
        delegate: LazyLoader {
            id: loader
            required property ShellScreen modelData
            active: ScreenRecorder.active && ScreenRecorder.state.region?.monitor === modelData.name
            component: PanelWindow {
                id: surface
                screen: loader.modelData
                color: "transparent"
                anchors { top: true; left: true; right: true; bottom: true }
                exclusionMode: ExclusionMode.Ignore
                exclusiveZone: 0
                WlrLayershell.namespace: "quickshell:recording-region"
                WlrLayershell.layer: WlrLayer.Overlay
                WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
                mask: Region {}
                readonly property var region: ScreenRecorder.state.region
                Shape {
                    x: (surface.region?.x || 0) - (surface.region?.monitorX || 0) - 3
                    y: (surface.region?.y || 0) - (surface.region?.monitorY || 0) - 3
                    width: (surface.region?.width || 0) + 6
                    height: (surface.region?.height || 0) + 6
                    ShapePath {
                        strokeColor: Appearance.m3colors.m3primaryFixed
                        strokeWidth: 2
                        strokeStyle: ShapePath.DashLine
                        dashPattern: [3, 3]
                        fillColor: "transparent"
                        startX: 0; startY: 0
                        PathLine { x: surface.region ? surface.region.width + 6 : 0; y: 0 }
                        PathLine { x: surface.region ? surface.region.width + 6 : 0; y: surface.region ? surface.region.height + 6 : 0 }
                        PathLine { x: 0; y: surface.region ? surface.region.height + 6 : 0 }
                        PathLine { x: 0; y: 0 }
                    }
                }
            }
        }
    }
}
