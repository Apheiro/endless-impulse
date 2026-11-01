pragma Singleton
pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import qs
import qs.modules.shared

Singleton {
    id: root
    property bool editing: false
    property string screenName: ""
    property string selectedKey: ""
    property var draft: ({version: 2, items: [], centerKey: ""})
    readonly property var catalog: [
        {type:"flex",name:Translation.tr("Flexible space"),icon:"width_full",multiple:true},
        {type:"spacer",name:Translation.tr("Fixed space"),icon:"space_bar",multiple:true},
        {type:"separator",name:Translation.tr("Separator"),icon:"vertical_align_center",multiple:true},
        {type:"sidebarLeft",name:Translation.tr("Left sidebar"),icon:"left_panel_open"},
        {type:"activeWindow",name:Translation.tr("Active window"),icon:"web_asset"},
        {type:"resources",name:Translation.tr("CPU & memory"),icon:"memory"},
        {type:"media",name:Translation.tr("Media player"),icon:"music_note"},
        {type:"workspaces",name:Translation.tr("Workspaces"),icon:"view_carousel"},
        {type:"clock",name:Translation.tr("Clock & calendar"),icon:"schedule"},
        {type:"utilities",name:Translation.tr("Utility buttons"),icon:"tune"},
        {type:"battery",name:Translation.tr("Battery"),icon:"battery_full"},
        {type:"weather",name:Translation.tr("Weather"),icon:"partly_cloudy_day"},
        {type:"tray",name:Translation.tr("System tray"),icon:"apps"},
        {type:"status",name:Translation.tr("Right panel"),icon:"right_panel_open"},
        {type:"search",name:Translation.tr("Search"),icon:"search"},
        {type:"networkSpeed",name:Translation.tr("Network speed"),icon:"network_check"},
        {type:"updates",name:Translation.tr("System updates"),icon:"system_update"},
        {type:"power",name:Translation.tr("Session & power"),icon:"power_settings_new"},
        {type:"profile",name:Translation.tr("Power profile"),icon:"bolt"},
        {type:"keyboard",name:Translation.tr("Keyboard layout"),icon:"keyboard"},
        {type:"recording",name:Translation.tr("Recording"),icon:"videocam"}
    ]
    readonly property var saved: normalize(Config.options.bar.layout ?? defaults())
    readonly property var layout: editing ? draft : saved
    readonly property bool customized: Config.options.bar.layout !== null
    readonly property var selected: locate(selectedKey)?.item ?? null
    Connections {
        target: Config.options.bar
        function onIndependentLayoutsChanged() { root.cancel(); }
    }

    function storedFor(name) {
        const perScreen = Config.options.bar.layoutsByScreen;
        if (Config.options.bar.independentLayouts && name && perScreen?.[name] !== undefined)
            return perScreen[name];
        return Config.options.bar.layout;
    }
    function savedFor(name) { return normalize(storedFor(name) ?? defaults()); }
    function customizedFor(name) { return storedFor(name) !== null; }
    function layoutFor(name) {
        return editing && (!Config.options.bar.independentLayouts || name === screenName)
            ? draft : savedFor(name);
    }
    function setIndependent(value) {
        if (Config.options.bar.independentLayouts === value) return;
        cancel();
        // Keep both shared and per-monitor layouts, so switching modes is reversible.
        Config.options.bar.independentLayouts = value;
    }

    function defaults() {
        return migrate({
            left: ["sidebarLeft", "activeWindow"].map(type => ({key: type, type})),
            center: ["resources", "media", "workspaces", "clock", "utilities", "battery"].map(type => ({key: type, type})),
            right: [...(Config.options.bar.weather.enable ? ["weather"] : []), "tray", "status"].map(type => ({key: type, type}))
        });
    }
    function info(type) {
        return catalog.find(item => item.type === type) || {type, name: type, icon: "widgets"};
    }
    function canCenter(item) {
        return !!item && !["flex", "spacer", "separator"].includes(item.type);
    }
    // JsonAdapter restores JSON arrays as Qt sequence wrappers. Array.isArray()
    // returns false for those lists even though they are iterable, so convert
    // them before deciding whether a persisted layout is an older format.
    function asArray(value) {
        if (Array.isArray(value)) return value;
        if (value && typeof value !== "string" && typeof value.length === "number")
            return Array.from(value);
        return [];
    }
    // Read old three-zone preferences without rewriting them until Save.
    function migrate(value) {
        const left = asArray(value?.left);
        const center = asArray(value?.center);
        const right = asArray(value?.right);
        const used = new Set([...left, ...center, ...right].map(item => item?.key));
        function gap(name) {
            let key = name;
            while (used.has(key)) key += "-";
            used.add(key);
            return {key, type: "flex"};
        }
        const anchor = center.find(item => item?.type === "clock") || center.find(item => canCenter(item));
        return {version: 2, items: [...left, gap("layout-flex-before"), ...center, gap("layout-flex-after"), ...right], centerKey: anchor?.key ?? ""};
    }
    function normalize(value) {
        const source = value?.items && typeof value.items.length === "number"
            ? {items: asArray(value.items), centerKey: value.centerKey}
            : migrate(value);
        const items = [], keys = new Set(), types = new Set();
        for (const item of source.items) {
            const known = catalog.find(row => row.type === item?.type);
            if (!known || typeof item.key !== "string" || !item.key || keys.has(item.key) || (!known.multiple && types.has(item.type))) continue;
            const next = {key: item.key, type: item.type};
            if (item.type === "spacer") next.size = Math.max(4, Math.min(600, Math.round(Number(item.size) || 24)));
            items.push(next);
            keys.add(item.key);
            types.add(item.type);
        }
        const anchor = items.find(item => item.key === source.centerKey);
        return {version: 2, items, centerKey: canCenter(anchor) ? anchor.key : ""};
    }
    function available(type) {
        return !!info(type).multiple || !layout.items.some(item => item.type === type);
    }
    function begin(name) {
        if (Config.options.bar.vertical) return;
        const target = name || Quickshell.screens[0]?.name || "";
        if (!editing || target !== screenName) draft = savedFor(target);
        screenName = target;
        selectedKey = "";
        editing = true;
        GlobalStates.sidebarRightOpen = false;
        GlobalStates.sidebarLeftOpen = false;
        QuickPanelState.dismiss();
    }
    function cancel() { editing = false; selectedKey = ""; }
    function save() {
        if (!editing) return;
        const next = normalize(draft);
        if (!Config.options.bar.independentLayouts && next.items.some(item => item.type === "weather"))
            Config.options.bar.weather.enable = true;
        if (Config.options.bar.independentLayouts && screenName) {
            const layouts = Object.assign({}, Config.options.bar.layoutsByScreen);
            layouts[screenName] = next;
            Config.options.bar.layoutsByScreen = layouts;
        } else Config.options.bar.layout = next;
        editing = false;
        selectedKey = "";
    }
    function resetDraft() { draft = normalize(defaults()); selectedKey = ""; }
    function restoreSaved(name = "") {
        cancel();
        if (Config.options.bar.independentLayouts && name) {
            const layouts = Object.assign({}, Config.options.bar.layoutsByScreen);
            layouts[name] = null;
            Config.options.bar.layoutsByScreen = layouts;
        } else Config.options.bar.layout = null;
    }
    function locate(key) {
        const index = draft.items.findIndex(item => item.key === key);
        return index < 0 ? null : {index, item: draft.items[index]};
    }
    // Index is in the final list, after the moving entry has been removed.
    function drop(type, key, index) {
        if (!editing) return false;
        const found = key ? locate(key) : null;
        if (key && !found) return false;
        if (!found && (!catalog.some(item => item.type === type) || !available(type))) return false;
        const next = normalize(draft);
        const item = found ? next.items.splice(found.index, 1)[0] : {key: type + "-" + Date.now() + "-" + Math.random().toString(36).slice(2, 7), type};
        if (type === "spacer" && item.size === undefined) item.size = 24;
        next.items.splice(Math.max(0, Math.min(next.items.length, index)), 0, item);
        draft = next;
        selectedKey = item.key;
        return true;
    }
    function remove(key) {
        const found = locate(key);
        if (!editing || !found) return;
        const next = normalize(draft);
        next.items.splice(found.index, 1);
        if (next.centerKey === key) next.centerKey = "";
        draft = next;
        if (selectedKey === key) selectedKey = "";
    }
    function moveBy(key, offset) {
        const found = locate(key);
        if (found) drop(found.item.type, key, Math.max(0, Math.min(draft.items.length - 1, found.index + offset)));
    }
    function setCenter(key) {
        if (!editing || (key && !canCenter(locate(key)?.item))) return;
        const next = normalize(draft);
        next.centerKey = key;
        draft = next;
    }
    function resizeSpacer(key, size) {
        const found = locate(key);
        if (!editing || found?.item.type !== "spacer" || !Number.isFinite(Number(size))) return;
        const next = normalize(draft);
        next.items[found.index].size = Math.max(4, Math.min(600, Math.round(Number(size))));
        draft = next;
    }
    function requestEditor(name = "") {
        const command = ["python3", Quickshell.shellPath("scripts/shell/control.py"), "ipc", "barEditor"];
        Quickshell.execDetached(name ? [...command, "openOnScreen", name] : [...command, "open"]);
    }
}
