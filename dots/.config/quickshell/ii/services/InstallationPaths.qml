pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import qs.modules.common

Singleton {
    id: root
    property var groups: []
    property string error: ""
    property bool loaded: false
    readonly property bool busy: worker.running

    function records() {
        const result = [];
        const titles = {configuration: Translation.tr("Configuration"), interface: Translation.tr("Interface"), data: Translation.tr("Local data")};
        const icons = {configuration: "tune", interface: "deployed_code", data: "hard_drive"};
        function add(group, title, path, description, tags, kind = "directory") {
            if (path) result.push({group: group, groupTitle: titles[group], groupIcon: icons[group], title: title, path: path,
                description: description, tags: tags, kind: kind, icon: kind === "file" ? "draft" : "folder"});
        }
        const config = Directories.config.replace(/^file:\/\//, "");
        const state = Quickshell.env("XDG_STATE_HOME") || Directories.home.replace(/^file:\/\//, "") + "/.local/state";
        const data = Quickshell.env("XDG_DATA_HOME") || Directories.home.replace(/^file:\/\//, "") + "/.local/share";
        function tr(text) { return Translation.tr(text); }
        add("configuration", "Artificial Impulse", Directories.shellConfig, tr("Personal desktop preferences and integrations"), [tr("Settings"), tr("Shortcuts"), tr("Icons")]);
        add("configuration", "config.json", Config.filePath, tr("Appearance, panels and feature preferences"), [tr("Settings")], "file");
        add("configuration", "shortcuts.lua", Directories.shellConfig + "/shortcuts.lua", tr("Personal keyboard and mouse shortcuts"), [tr("Shortcuts")], "file");
        add("configuration", "hyprland.json", Directories.shellConfig + "/hyprland.json", tr("Saved monitor, window and input settings"), ["Hyprland"], "file");
        add("configuration", "hyprland.lua", Directories.shellConfig + "/hyprland.lua", tr("Generated Hyprland overrides"), ["Hyprland"], "file");
        add("configuration", "icons.json", Directories.shellConfig + "/icons.json", tr("Selected icon theme and application overrides"), [tr("Icons")], "file");
        add("configuration", tr("Custom actions"), Directories.userActions, tr("Personal launcher commands"), [tr("Search")]);
        add("configuration", tr("AI prompts"), Directories.userAiPrompts, tr("Personal assistant instructions"), ["AI"]);
        add("configuration", "Hyprland", config + "/hypr", tr("Compositor configuration"), [tr("Windows"), tr("Monitors"), tr("Input")]);
        add("configuration", "hyprland.lua", config + "/hypr/hyprland.lua", tr("Compositor entry point"), ["Hyprland"], "file");
        add("configuration", tr("Hyprland services"), config + "/hypr/hyprland/services", tr("Settings loaders and shortcut integration"), ["Hyprland"]);
        add("configuration", "Matugen", config + "/matugen", tr("Color generation configuration and templates"), [tr("Themes"), "GTK", "Qt"]);
        add("configuration", "config.toml", config + "/matugen/config.toml", tr("Color templates and their output paths"), ["Matugen"], "file");
        add("configuration", tr("Templates"), config + "/matugen/templates", tr("Source templates for application colors"), ["Matugen"]);
        for (const environment of ["gtk-3.0", "gtk-4.0", "qt5ct", "qt6ct"])
            add("configuration", environment, config + "/" + environment, tr("Application theme preferences"), [tr("Themes"), tr("Icons")]);
        for (const entry of IconTheme.paths.concat(IconTheme.colorPaths)) {
            if (entry.path === data + "/icons/ArtificialImpulse/index.theme") continue;
            add("configuration", entry.path.split("/").pop(), entry.path, entry.name, [entry.name], entry.name === "GNOME / GSettings" ? "directory" : "file");
        }
        add("interface", tr("Shell source"), Quickshell.shellDir, tr("Running interface and its entry points"), ["QML", "JavaScript"]);
        for (const part of [
            ["shell.qml", tr("Desktop entry point"), "file"], ["settings.qml", tr("Settings window"), "file"],
            ["modules", tr("Interface components"), "directory"], ["modules/ii", tr("Bar, dock, overview and panels"), "directory"],
            ["modules/settings", tr("Settings pages"), "directory"], ["modules/common", tr("Shared components and appearance"), "directory"],
            ["services", tr("Session and system integrations"), "directory"], ["scripts", tr("Automation and external tools"), "directory"],
            ["assets", tr("Bundled images, fonts and resources"), "directory"], ["defaults", tr("Default configuration and prompts"), "directory"],
            ["translations", tr("Interface translations"), "directory"]])
            add("interface", part[0].split("/").pop(), Quickshell.shellPath(part[0]), part[1], [], part[2]);
        add("data", tr("Wallpaper"), Config.options.background.wallpaperPath, tr("Current desktop background"), [tr("Wallpaper")], "file");
        add("data", tr("Wallpaper thumbnail"), Config.options.background.thumbnailPath, tr("Background preview image"), [tr("Wallpaper")], "file");
        add("data", tr("Session preferences"), Persistent.filePath, tr("Remembered session state"), [tr("State")], "file");
        add("data", tr("Shell state"), Directories.state, tr("Persistent session data and generated resources"), [tr("State")]);
        for (const entry of [
            [tr("Tasks"), Directories.todoPath, tr("Saved task list"), "file"], [tr("Notes"), Directories.notesPath, tr("Personal notes"), "file"],
            [tr("Chats"), Directories.aiChats, tr("Saved assistant conversations"), "directory"],
            [tr("Generated colors"), Directories.generatedMaterialThemePath, tr("Current shell palette"), "file"]])
            add("data", entry[0], entry[1], entry[2], [tr("State")], entry[3]);
        add("data", tr("Desktop state"), state + "/artificial-impulse", tr("Recovery information and integration state"), ["Hyprland", tr("Backups")]);
        add("data", tr("Display recovery"), state + "/artificial-impulse/desktop", tr("Display previews, last good configuration and backups"), [tr("Monitors")]);
        add("data", tr("Icon backups"), state + "/artificial-impulse/icon-backups", tr("Configuration copies made before applying icon changes"), [tr("Icons")]);
        add("data", "minimized.json", state + "/artificial-impulse/minimized.json", tr("Original workspaces of minimized windows"), [tr("Dock")], "file");
        add("data", "runtime.json", state + "/dots-hyperland/runtime.json", tr("Active shell source and launcher"), [tr("Runtime")], "file");
        add("data", tr("Shell cache"), Directories.cache, tr("Temporary files that can be regenerated"), [tr("Cache")]);
        for (const entry of [
            [tr("Site icons"), Directories.favicons, tr("Launcher and search favicons")],
            [tr("Cover art"), Directories.coverArt, tr("Media artwork")],
            [tr("Image previews"), Directories.booruPreviews, tr("Cached image search previews")],
            [tr("Formulas"), Directories.latexOutput, tr("Rendered mathematical expressions")],
            [tr("Conflict detection"), Directories.conflictCachePath, tr("Session integration checks")]])
            add("data", entry[0], entry[1], entry[2], [tr("Cache")]);
        add("data", tr("Notifications"), Directories.notificationsPath, tr("Saved notification history"), [tr("Notifications")], "file");
        const baseTheme = IconTheme.themes.find(theme => theme.id === IconTheme.theme);
        if (baseTheme) add("data", baseTheme.name, baseTheme.path, tr("Installed base icon theme inherited by Artificial Impulse"), [tr("Icons"), tr("Themes")]);
        add("data", tr("Personal icons"), data + "/icons", tr("User-installed icon themes"), [tr("Icons")]);
        add("data", "ArtificialImpulse", data + "/icons/ArtificialImpulse", tr("Icon theme inheritance and custom application images"), [tr("Icons")]);
        add("data", "index.theme", data + "/icons/ArtificialImpulse/index.theme", tr("Selected base theme and fallback chain"), [tr("Icons")], "file");
        add("data", tr("Application entries"), data + "/applications", tr("Personal launchers and application icon overrides"), [tr("Apps"), tr("Icons")]);
        add("data", tr("Color schemes"), data + "/color-schemes", tr("Generated and installed KDE color schemes"), ["Qt", "KDE"]);
        add("data", tr("Temporary media"), "/tmp/quickshell/media", tr("Short-lived capture and clipboard files"), [tr("Temporary")]);
        for (const entry of [[tr("Images"), Directories.tempImages], [tr("Clipboard"), Directories.cliphistDecode], [tr("Screenshots"), Directories.screenshotTemp]])
            add("data", entry[0], entry[1], tr("Temporary media files"), [tr("Temporary")]);
        add("data", tr("Recordings"), Config.options.screenRecord.savePath, tr("Destination selected for screen recordings"), [tr("Capture")]);
        add("data", tr("Screenshots"), Config.options.screenSnip.savePath, tr("Destination selected for saved screenshots"), [tr("Capture")]);
        add("data", tr("Downloaded images"), Directories.booruDownloads, tr("Saved image search results"), [tr("Images")]);
        add("configuration", tr("Custom translations"), Directories.shellConfig + "/translations", tr("Personal interface translations"), [tr("Language")]);
        add("interface", tr("Default AI prompts"), Directories.defaultAiPrompts, tr("Bundled assistant instructions"), ["AI"]);
        add("data", tr("Private image downloads"), Directories.booruDownloadsNsfw, tr("Separate destination for filtered image results"), [tr("Images")]);
        add("data", tr("AI request files"), "/tmp/quickshell/ai", tr("Temporary assistant request scripts"), [tr("Temporary"), "AI"]);
        add("data", tr("Account avatar"), Directories.userAvatarPathAccountsService, tr("System account picture"), [tr("Profile")], "file");
        add("data", tr("Personal avatar"), Directories.userAvatarPathRicersAndWeirdSystems, tr("Personal account picture fallback"), [tr("Profile")], "file");
        add("data", tr("Personal avatar icon"), Directories.userAvatarPathRicersAndWeirdSystems2, tr("Alternative account picture fallback"), [tr("Profile")], "file");
        return result;
    }
    function refresh() {
        if (busy) return;
        worker.payload = JSON.stringify(records());
        error = "";
        worker.received = false;
        worker.stdinEnabled = true;
        worker.running = true;
    }
    Process {
        id: worker
        property string payload: ""
        property bool received: false
        command: ["python3", Quickshell.shellPath("scripts/shell/path_map.py")]
        onStarted: { write(payload); stdinEnabled = false; }
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const result = JSON.parse(text);
                    worker.received = true;
                    if (!result.ok) { root.error = result.error; return; }
                    root.groups = result.groups;
                    root.loaded = true;
                } catch (error) { root.error = String(error); }
            }
        }
        onExited: (code, status) => { if (!received) root.error = "Could not read installation paths."; }
    }
    Connections {
        target: IconTheme
        function onPathsChanged() { if (root.loaded) refreshTimer.restart(); }
    }
    Timer { id: refreshTimer; interval: 100; onTriggered: root.refresh() }
}
