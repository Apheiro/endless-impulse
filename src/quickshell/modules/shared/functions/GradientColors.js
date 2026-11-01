.pragma library

function parse(value) {
    const input = String(value || "").trim();
    const valid = /^(?:rgba\([0-9a-f]{8}\)|rgb\([0-9a-f]{6}\))(?:\s+(?:rgba\([0-9a-f]{8}\)|rgb\([0-9a-f]{6}\))){0,9}(?:\s+\d{1,3}deg)?$/i.test(input);
    const colors = [];
    const pattern = /(rgba|rgb)\(([0-9a-f]+)\)/gi;
    let match;
    while ((match = pattern.exec(input)) !== null) colors.push(match[2].toLowerCase() + (match[1].toLowerCase() === "rgb" ? "ff" : ""));
    const angle = input.match(/\s(\d+)deg$/i);
    return {valid: valid && (!angle || Number(angle[1]) <= 360), colors: valid ? colors : [], angle: angle ? Number(angle[1]) : 0, hasAngle: !!angle};
}

function qtColor(hex) {
    return "#" + hex.slice(6, 8) + hex.slice(0, 6);
}

function fromColor(color) {
    return [color.r, color.g, color.b, color.a].map(channel => Math.round(Math.max(0, Math.min(1, channel)) * 255).toString(16).padStart(2, "0")).join("");
}

function format(colors, angle, includeAngle) {
    return colors.map(hex => "rgba(" + hex + ")").join(" ") + (colors.length > 1 || includeAngle ? " " + Math.round(angle) + "deg" : "");
}
