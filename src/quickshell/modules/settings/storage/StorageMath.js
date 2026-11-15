.pragma library

// Pure accounting shared by the chart, legend and acceptance tests.
function chart(view, volume) {
    if (!["complete", "complete-with-warnings"].includes(view?.state))
        return {segments: [], total: 0, mode: "none", known: 0, unknown: 0, excess: 0};
    if (!volume?.mounted)
        return {segments: [], total: 0, mode: "none", known: 0, unknown: 0, excess: 0};
    if (!volume.accessible && view)
        return {segments: view.segments || [], total: view.bytes, mode: "directory", known: view.bytes, unknown: 0, excess: 0};
    if (!volume.accessible) return {segments: [], total: 0, mode: "none", known: 0, unknown: 0, excess: 0};
    const atMount = !!view && view.path === volume.mount;
    const known = view?.bytes || 0;
    const excess = atMount ? Math.max(0, known - volume.used) : 0;
    const limited = view.coverageIncomplete || view.coverageUncertain || view.state === "complete-with-warnings";
    const mode = !limited && atMount && !excess ? "volume" : "directory";
    const warningDifference = limited && atMount ? Math.max(0, volume.used - known) : 0;
    const parts = (view?.segments || []).map(p => Object.assign({}, p));
    const unknown = mode === "volume" ? Math.max(0, volume.used - known) : 0;
    if (unknown) parts.push({kind: "unknown", name: "Not analyzed / not attributable", path: "", bytes: unknown});
    if (mode === "volume") {
        if (volume.reserved) parts.push({kind: "reserved", name: "Reserved", path: "", bytes: volume.reserved});
        if (volume.available) parts.push({kind: "free", name: "Free", path: "", bytes: volume.available});
    }
    return {segments: parts, total: mode === "volume" ? volume.total : known,
            mode, known, unknown, excess, warningDifference};
}
function colorIndex(path) {
    let hash = 0;
    for (let i = 0; i < path.length; i++) hash = ((hash << 5) - hash + path.charCodeAt(i)) | 0;
    return (hash >>> 0) % 7;
}

// Geometry never inflates the allocation. A separate marker represents subpixels.
function boundedRatio(bytes, total) {
    if (!Number.isFinite(bytes) || !Number.isFinite(total) || bytes <= 0 || total <= 0) return 0;
    return Math.max(0, Math.min(1, bytes / total));
}
