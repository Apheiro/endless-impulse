.pragma library

// Shared with the shortcut guide. Keep the actual trigger separate from its label.
var macSymbols = {
    Ctrl: "󰘴", Alt: "󰘵", Shift: "󰘶", Space: "󱁐", Tab: "↹", Equal: "󰇼", Minus: "",
    Print: "", BackSpace: "󰭜", Delete: "⌦", Return: "󰌑", Period: ".", Escape: "⎋"
};
var functionSymbols = {
    F1: "󱊫", F2: "󱊬", F3: "󱊭", F4: "󱊮", F5: "󱊯", F6: "󱊰",
    F7: "󱊱", F8: "󱊲", F9: "󱊳", F10: "󱊴", F11: "󱊵", F12: "󱊶"
};
var mouseSymbols = {mouse_up: "󱕐", mouse_down: "󱕑", "mouse:272": "L󰍽", "mouse:273": "R󰍽", "Scroll ↑/↓": "󱕒", "Page_↑/↓": "⇞/⇟"};
var mediaSymbols = {
    XF86AudioRaiseVolume: "󰕾", XF86AudioLowerVolume: "󰖀", XF86AudioMute: "󰝟", XF86AudioMicMute: "󰍭",
    XF86AudioPlay: "󰐊", XF86AudioPause: "󰏤", XF86AudioNext: "󰒭", XF86AudioPrev: "󰒮",
    XF86MonBrightnessUp: "󰃠", XF86MonBrightnessDown: "󰃞"
};
function substitutions(options) {
    return Object.assign({Super: options.superKey || "", mouse_up: "Scroll ↓", mouse_down: "Scroll ↑",
        "mouse:272": "LMB", "mouse:273": "RMB", "mouse:275": "MouseBack", Slash: "/", Hash: "#", Return: "Enter"},
        mediaSymbols, options.useMacSymbol ? macSymbols : {}, options.useFnSymbol ? functionSymbols : {},
        options.useMouseSymbol ? mouseSymbols : {});
}
function modifiers(mask) {
    var result = [];
    var order = [[2, "Ctrl"], [6, "Super"], [0, "Shift"], [3, "Alt"], [1, "Caps"], [4, "Mod2"], [5, "Mod3"], [7, "Mod5"]];
    for (var i = 0; i < order.length; i++) if (mask & (1 << order[i][0])) result.push(order[i][1]);
    return result;
}
function canonical(key) {
    var aliases = {SUPER: "Super", MOD4: "Super", WIN: "Super", CTRL: "Ctrl", CONTROL: "Ctrl", ALT: "Alt", SHIFT: "Shift", MOD2: "Mod2", MOD3: "Mod3", MOD5: "Mod5"};
    return aliases[key.toUpperCase()] || key;
}
function tokens(combination, options) {
    var parts = (combination || "").split("+").map(function(part) { return part.trim(); }).filter(function(part) { return part.length > 0; });
    if (!parts.length) return [];
    var substitutionsMap = substitutions(options);
    var trigger = parts.pop();
    var mods = parts.map(function(part) { var key = canonical(part); return substitutionsMap[key] || key; });
    if (!options.splitButtons && mods.length) mods = [mods.join(" ")];
    var result = mods.map(function(text) { return {text: text, separator: false}; });
    if (mods.length) result.push({text: "+", separator: true});
    var label = substitutionsMap[trigger] || trigger;
    if (/^SUPER_[LR]$/i.test(trigger)) label = substitutionsMap.Super + " " + trigger.slice(-1).toUpperCase();
    result.push({text: label, separator: false});
    return result;
}
function category(entry) {
    if (entry.category) return entry.category;
    var description = entry.description || "";
    var colon = description.indexOf(":");
    return colon > 0 ? description.slice(0, colon).trim() : "Other";
}
function description(entry) {
    if (!entry.description) return entry.default;
    return entry.description.split(" / ").map(function(part) {
        var colon = part.indexOf(":");
        return colon > 0 ? part.slice(colon + 1).trim() : part;
    }).join(" / ");
}
function groups(entries, query) {
    var terms = (query || "").toLowerCase().trim().split(/\s+/);
    var result = [];
    entries.forEach(function(entry) {
        var name = category(entry);
        var haystack = [name, entry.description, entry.current, entry.default, entry.submap].join(" ").toLowerCase();
        if (!terms.every(function(term) { return haystack.indexOf(term) !== -1; })) return;
        var group = result.find(function(group) { return group.name === name; });
        if (!group) { group = {name: name, entries: []}; result.push(group); }
        group.entries.push(entry);
    });
    return result;
}
