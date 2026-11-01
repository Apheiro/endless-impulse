import QtQuick
import Quickshell

import qs.modules.shared
import qs.modules.windowsStyle.actionCenter
import qs.modules.windowsStyle.background
import qs.modules.windowsStyle.bar
import qs.modules.windowsStyle.lock
import qs.modules.windowsStyle.notificationCenter
import qs.modules.windowsStyle.notificationPopup
import qs.modules.windowsStyle.onScreenDisplay
// import qs.modules.windowsStyle.overlay
import qs.modules.windowsStyle.polkit
import qs.modules.windowsStyle.screenSnip
import qs.modules.windowsStyle.startMenu
import qs.modules.windowsStyle.sessionScreen
import qs.modules.windowsStyle.taskView

// Fallbacks
import qs.modules.desktop.cheatsheet
import qs.modules.desktop.onScreenKeyboard
import qs.modules.desktop.overlay
import qs.modules.desktop.screenTranslator
import qs.modules.desktop.wallpaperSelector

Scope {
    PanelLoader { component: WaffleActionCenter {} }
    PanelLoader { component: WaffleBar {} }
    PanelLoader { component: WaffleBackground {} }
    PanelLoader { component: WaffleLock {} }
    PanelLoader { component: WaffleNotificationCenter {} }
    PanelLoader { component: WaffleNotificationPopup {} }
    PanelLoader { component: WaffleOSD {} }
    // PanelLoader { component: WaffleOverlay {} }
    PanelLoader { component: WafflePolkit {} }
    PanelLoader { component: WScreenSnip {} }
    PanelLoader { component: WaffleStartMenu {} }
    PanelLoader { component: WaffleSessionScreen {} }
    PanelLoader { component: WaffleTaskView {} }

    PanelLoader { component: Cheatsheet {} }
    PanelLoader { component: OnScreenKeyboard {} }
    PanelLoader { component: Overlay {} }
    PanelLoader { component: ScreenTranslator {} }
    PanelLoader { component: WallpaperSelector {} }
}
