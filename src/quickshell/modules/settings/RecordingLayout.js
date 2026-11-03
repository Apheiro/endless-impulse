.pragma library

// Every schema group remains reachable, including groups added by the helper.
function tabForGroup(group) {
    if (group === "Files" || group === "Capture") return 0;
    if (group === "Video") return 1;
    if (group === "Audio") return 2;
    return 3;
}

function groupsForTab(fields, tab) {
    const groups = [...new Set(fields.map(field => field.group))];
    const order = tab === 0 ? ["Capture", "Files"] : groups;
    return order.filter(group => groups.includes(group) && tabForGroup(group) === tab);
}

function fullWidth(field) {
    return !["bool", "int", "enum", "float"].includes(field.type);
}

function fieldsForGroup(fields, group) {
    // Session type belongs beside the capture target, before output naming.
    const selected = fields.filter(field => group === "Capture"
        ? field.group === group || field.key === "mode"
        : field.group === group && field.key !== "mode");
    return selected.filter(field => !fullWidth(field)).concat(selected.filter(fullWidth));
}
