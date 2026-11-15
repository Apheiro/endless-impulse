pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import qs.services
import qs.modules.shared
import qs.modules.shared.primitives.common
import "StorageMath.js" as Accounting

ColumnLayout {
    id: root
    property var view: Storage.view
    property var volume: Storage.selected
    readonly property var chart: Accounting.chart(view, volume)
    property int selectedNodeId: Storage.highlightedNodeId
    signal folderSelected(string path, int nodeId)
    signal othersSelected()
    Layout.minimumWidth: 0
    spacing: 10
    function segmentColor(segment) {
        const palette = [Appearance.colors.colPrimary, Appearance.m3colors.m3tertiary,
            Appearance.m3colors.m3secondary, Appearance.m3colors.m3primaryContainer,
            Appearance.m3colors.m3tertiaryContainer, Appearance.m3colors.m3secondaryContainer,
            Appearance.colors.colPrimaryHover];
        if (segment.kind === "free") return Appearance.colors.colSecondaryContainer;
        if (segment.kind === "unknown") return Appearance.colors.colOutlineVariant;
        if (segment.kind === "reserved") return Appearance.colors.colOutline;
        if (segment.kind === "files" || segment.kind === "metadata") return Appearance.m3colors.m3secondary;
        const slots = {}, used = {};
        (view?.segments || []).filter(s => s.kind === "folder").slice().sort((a,b) => (a.key || a.path).localeCompare(b.key || b.path)).forEach(s => {
            let slot = Accounting.colorIndex(s.key || s.path);
            while (used[slot]) slot = (slot + 1) % palette.length;
            used[slot] = true; slots[s.key || s.path] = slot;
        });
        return colorAgainst(readableFill(palette[slots[segment.key || segment.path] ?? Accounting.colorIndex(segment.key || segment.path || segment.kind)]), Appearance.colors.colLayer0, true);
    }
    function progressTrackColor() { return opaque(Appearance.colors.colSecondaryContainer); }
    function progressFillColor(segment, trackColor) { return colorAgainst(segmentColor(segment), trackColor, false); }
    function opaque(value) { const c = Qt.darker(value, 1); return Qt.rgba(c.r, c.g, c.b, 1); }
    // Theme-derived adjustment toward the most contrasting theme token keeps
    // the starting hue as far as possible. Text contrast is a separate check.
    function colorAgainst(value, background, requireText) {
        const source = opaque(value), track = opaque(background);
        function valid(c) { return contrast(c, track) >= 3.05 && (!requireText || contrast(c, contrastingText(c)) >= 4.5); }
        if (valid(source)) return source;
        const tokens = [Appearance.colors.colOnLayer0, Appearance.colors.colLayer0,
            Appearance.m3colors.m3onPrimary, Appearance.m3colors.m3onPrimaryContainer,
            Appearance.m3colors.m3onSecondary, Appearance.m3colors.m3onTertiary];
        const target = opaque(tokens.reduce((best, c) => contrast(c, track) > contrast(best, track) ? c : best));
        for (let step = 1; step <= 100; step++) {
            const t = step / 100;
            const c = Qt.rgba(source.r + (target.r - source.r) * t,
                source.g + (target.g - source.g) * t, source.b + (target.b - source.b) * t, 1);
            if (valid(c)) return c;
        }
        return target;
    }
    StyledText {
        Layout.fillWidth: true
        text: root.view?.coverageIncomplete || root.view?.state === "complete-with-warnings" ? Translation.tr("Counted allocation — incomplete coverage") + " · " + Storage.formatBytes(root.chart.total) + " · " + root.view.path
            : root.view?.coverageUncertain ? Translation.tr("Counted allocation — directory entries changed") + " · " + Storage.formatBytes(root.chart.total)
            : root.chart.mode === "directory" ? (root.view?.path || "") : Translation.tr("Volume capacity")
        textFormat: Text.PlainText
        elide: Text.ElideMiddle
        color: Appearance.colors.colOnLayer0
        font.weight: Font.DemiBold
    }
    Item {
        id: bar
        objectName: "storage-usage-bar"
        Layout.fillWidth: true
        implicitHeight: 46
        clip: true
        Accessible.role: Accessible.ProgressBar
        Accessible.name: Translation.tr("Storage by real folders")
        Accessible.description: root.chart.segments.map(s => root.label(s) + ": " + Storage.exact(s.bytes)).join("; ")
        Row {
            anchors.fill: parent
            Repeater {
                model: root.chart.segments
                delegate: Rectangle {
                    id: segment
                    required property var modelData
                    required property int index
                    objectName: "storage-segment-" + index
                    width: bar.width * Accounting.boundedRatio(modelData.bytes, root.chart.total)
                    height: bar.height
                    color: root.segmentColor(modelData)
                    border.width: modelData.kind === "folder" && modelData.nodeId === root.selectedNodeId ? 3 : 1
                    border.color: modelData.nodeId === root.selectedNodeId ? Appearance.colors.colOnLayer0 : root.contrastingText(color)
                    Accessible.role: Accessible.Button
                    Accessible.name: root.label(modelData) + ": " + Storage.exact(modelData.bytes)
                    StyledText {
                        anchors.fill: parent
                        anchors.margins: 7
                        text: segment.modelData.kind === "folder" ? segment.modelData.name : ""
                        textFormat: Text.PlainText
                        visible: parent.width > implicitWidth + 14
                        elide: Text.ElideRight
                        color: root.contrastingText(parent.color)
                        font.weight: Font.DemiBold
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: segment.modelData.kind === "folder" || segment.modelData.kind === "others" ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onClicked: root.activate(segment.modelData)
                    }
                }
            }
        }
    }
    Flow {
        Layout.fillWidth: true
        spacing: 8
        Repeater {
            model: root.chart.segments
            delegate: RippleButton {
                id: legend
                required property var modelData
                required property int index
                objectName: "storage-legend-" + index
                implicitWidth: Math.min(legendContent.implicitWidth + 16, root.width)
                implicitHeight: legendContent.implicitHeight + 10
                surfaceVisible: false
                Accessible.name: root.label(modelData) + ": " + Storage.exact(modelData.bytes)
                onClicked: root.activate(modelData)
                contentItem: RowLayout {
                    id: legendContent
                    spacing: 6
                    Rectangle { implicitWidth: 9; implicitHeight: 9; radius: 3; color: root.segmentColor(legend.modelData) }
                    StyledText {
                        Layout.fillWidth: true
                        text: root.label(legend.modelData) + "  " + Storage.formatBytes(legend.modelData.bytes)
                        textFormat: Text.PlainText
                        elide: Text.ElideMiddle
                        color: Appearance.colors.colOnLayer0
                        font.pixelSize: Appearance.font.pixelSize.smaller
                    }
                }
            }
        }
    }
    function label(segment) {
        return segment.kind === "folder" ? (segment.partial ? "≈ " : "") + (view?.path === "/" ? "/" + segment.name : segment.name) : Translation.tr(segment.name);
    }
    function activate(segment) {
        if (segment.kind === "folder") folderSelected(segment.path, segment.nodeId);
        else if (segment.kind === "others") othersSelected();
    }
    function luminance(value) {
        const c = Qt.darker(value, 1);
        function linear(v) { return v <= .04045 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); }
        return .2126 * linear(c.r) + .7152 * linear(c.g) + .0722 * linear(c.b);
    }
    function contrast(a, b) { const x = luminance(a), y = luminance(b); return (Math.max(x,y)+.05)/(Math.min(x,y)+.05); }
    function readableFill(value) {
        let color = Qt.darker(value, 1);
        for (let i = 0; i < 12 && contrast(color, contrastingText(color)) < 4.5; i++) {
            const lighter = Qt.lighter(color, 1.12), darker = Qt.darker(color, 1.12);
            color = contrast(lighter, contrastingText(lighter)) > contrast(darker, contrastingText(darker)) ? lighter : darker;
        }
        return color;
    }
    function contrastingText(color) {
        const source = luminance(color);
        const candidates = [Appearance.colors.colOnLayer0, Appearance.m3colors.m3onPrimary,
            Appearance.m3colors.m3onPrimaryContainer, Appearance.m3colors.m3onSecondary,
            Appearance.m3colors.m3onTertiary, Appearance.colors.colLayer0];
        return candidates.reduce((best, candidate) => {
            function contrast(c) { const l = luminance(c); return (Math.max(source,l)+.05)/(Math.min(source,l)+.05); }
            return contrast(candidate) > contrast(best) ? candidate : best;
        });
    }
}
