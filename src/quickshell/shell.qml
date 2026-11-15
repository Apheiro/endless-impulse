//@ pragma UseQApplication
//@ pragma Env QS_NO_RELOAD_POPUP=1
//@ pragma Env QT_QUICK_CONTROLS_STYLE=Basic
//@ pragma Env QT_QUICK_FLICKABLE_WHEEL_DECELERATION=10000

// Remove two slashes below and adjust the value to change the UI scale
////@ pragma Env QT_SCALE_FACTOR=1

import "modules/shared"
import "services"
import "shellVariants"
import qs.modules.shared.widgets
import qs.modules.desktop.quickPanels

import QtQuick
import QtQuick.Window
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland

ShellRoot {
    id: root

    // Stuff for every panel family
    ReloadPopup {}
    QuickPanel {}
    // Authentication is session-wide and survives layout family switches.
    LazyLoader {
        active: Config.ready
        component: PolkitPanel {}
    }

    Component.onCompleted: {
        registerRuntime.running = true
        InternalSurfaces.load()
        // Legacy X11 applications need a bridge to the shared StatusNotifier registry.
        Quickshell.execDetached(["sh", "-c", "command -v xembedsniproxy >/dev/null && (pidof xembedsniproxy >/dev/null || exec xembedsniproxy)"])
        AnimationSpeed.load()
        LayerEffects.load()
        MaterialThemeLoader.reapplyTheme()
        Hyprsunset.load()
        FirstRunExperience.load()
        ConflictKiller.load()
        Cliphist.refresh()
        Wallpapers.load()
        Updates.load()
    }

    Process {
        id: registerRuntime
        command: ["python3", Quickshell.shellPath("scripts/shell/control.py"), "register",
            Quickshell.shellPath("shell.qml"), "qs"]
    }

    IpcHandler {
        target: "health"
        function ping(): string { return "ok"; }
    }


    // Shell variants (legacy persisted ids "ii" and "waffle" stay supported).
    property list<string> families: ["ii", "waffle"]
    function cyclePanelFamily() {
        const currentIndex = families.indexOf(Config.options.panelFamily)
        const nextIndex = (currentIndex + 1) % families.length
        Config.options.panelFamily = families[nextIndex]
    }

    component PanelFamilyLoader: LazyLoader {
        required property string identifier
        property bool extraCondition: true
        active: Config.ready && Config.options.panelFamily === identifier && extraCondition
    }
    
    PanelFamilyLoader {
        identifier: "ii"
        component: DesktopShell {}
    }

    PanelFamilyLoader {
        identifier: "waffle"
        component: WindowsStyleShell {}
    }


    // Shortcuts
    IpcHandler {
        target: "panelFamily"

        function cycle(): void {
            root.cyclePanelFamily()
        }
    }

    GlobalShortcut {
        name: "panelFamilyCycle"
        description: "Cycles panel family"

        onPressed: root.cyclePanelFamily()
    }
}

