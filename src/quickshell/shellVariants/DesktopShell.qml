import QtQuick
import Quickshell

import qs.modules.shared
import qs.modules.desktop.background
import qs.modules.desktop.bar
import qs.modules.desktop.cheatsheet
import qs.modules.desktop.dock
import qs.modules.desktop.lock
import qs.modules.desktop.mediaControls
import qs.modules.desktop.notificationPopup
import qs.modules.desktop.onScreenDisplay
import qs.modules.desktop.onScreenKeyboard
import qs.modules.desktop.overview
import qs.modules.desktop.polkit
import qs.modules.desktop.recording
import qs.modules.desktop.regionSelector
import qs.modules.desktop.screenCorners
import qs.modules.desktop.screenTranslator
import qs.modules.desktop.sessionScreen
import qs.modules.desktop.sidebarLeft
import qs.modules.desktop.sidebarRight
import qs.modules.desktop.overlay
import qs.modules.desktop.verticalBar
import qs.modules.desktop.wallpaperSelector

Scope {
    PanelLoader { extraCondition: !Config.options.bar.vertical; component: Bar {} }
    PanelLoader { component: Background {} }
    PanelLoader { component: Cheatsheet {} }
    PanelLoader { extraCondition: Config.options.dock.enable; component: Dock {} }
    PanelLoader { component: Lock {} }
    PanelLoader { component: MediaControls {} }
    PanelLoader { component: NotificationPopup {} }
    PanelLoader { component: OnScreenDisplay {} }
    PanelLoader { component: OnScreenKeyboard {} }
    PanelLoader { component: Overlay {} }
    PanelLoader { component: Overview {} }
    PanelLoader { component: Polkit {} }
    PanelLoader { component: RegionSelector {} }
    RecordingOverlay {}
    PanelLoader { component: ScreenCorners {} }
    PanelLoader { component: ScreenTranslator {} }
    PanelLoader { component: SessionScreen {} }
    PanelLoader { component: SidebarLeft {} }
    PanelLoader { component: SidebarRight {} }
    PanelLoader { extraCondition: Config.options.bar.vertical; component: VerticalBar {} }
    PanelLoader { component: WallpaperSelector {} }
}
