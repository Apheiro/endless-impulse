pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import Quickshell
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets

Item {
    id: root
    objectName: "configured-bar-content"
    property bool editing: false
    property bool compact: width < 1500
    property string screenName: ""
    readonly property var layout: BarLayout.layoutFor(screenName)
    readonly property real itemSpacing: 4
    readonly property real barHeight: Appearance.sizes.barHeight
    readonly property real outerMargin: Config.options.bar.cornerStyle === 1 ? Appearance.sizes.hyprlandGapsOut : 0
    readonly property var editorSurface: drawer
    readonly property real drawerHeight: Math.min(390, (root.QsWindow.window?.screen?.height ?? 900) * .45)
    implicitHeight: barHeight + (editing ? drawerHeight + Appearance.sizes.elevationMargin * 2 : 0)
    readonly property var entries: {
        const items = layout.items;
        if (ScreenRecorder.active && !items.some(item => ["utilities", "recording"].includes(item.type)))
            return [...items, {key: "__active-recording", type: "recording", locked: true}];
        return items;
    }
    readonly property var displayEntries: {
        if (!dragging || !hoverOnBar || !drag) return entries;
        // The pinned tile stays in its stable host at screen center; moving it
        // changes which neighbours belong before/after that host.
        if (drag.key && drag.key === layout.centerKey) {
            const next = entries.filter(item => item.key !== drag.key);
            next.splice(hoverIndex, 0, entries.find(item => item.key === drag.key));
            return next;
        }
        const next = entries.slice();
        const remaining = entries.filter(item => item.key !== drag.key && !item.locked);
        const target = remaining[hoverIndex];
        const index = target ? next.findIndex(item => item.key === target.key) : next.length;
        next.splice(index, 0, {key: "__drag-gap", type: "spacer", placeholder: true});
        return next;
    }
    readonly property int anchorIndex: displayEntries.findIndex(item => item.key === layout.centerKey)
    property var drag: null
    property bool dragging: false
    property point pointer: Qt.point(0, 0)
    property bool hoverOnBar: false
    property bool hoverOnCatalog: false
    property int hoverIndex: 0
    readonly property real dragWidth: drag?.key ? drag.width : (catalogPreview.item?.implicitWidth ?? 140)

    function tilesInOrder() {
        const tiles = {};
        for (const row of [before.row, after.row]) {
            for (const child of row.children) if (child.instanceKey !== undefined) tiles[child.instanceKey] = child;
        }
        if (anchorIndex >= 0) tiles[anchorTile.instanceKey] = anchorTile;
        return displayEntries.map(item => tiles[item.key]).filter(tile => tile && tile.visible && !tile.collapsed);
    }
    // Group actual neighbours, including across the optional center anchor.
    // Hidden modules are skipped; spaces and separators always delimit a group.
    function tileX(tile) {
        if (tile === anchorTile) return tile.x;
        const flow = tile.parent === before.row ? before : after;
        return flow.x + flow.row.x - flow.contentX + tile.x;
    }
    function adjacentModule(tile, direction) {
        const structural = ["spacer", "flex", "separator"];
        if (structural.includes(tile.entry.type)) return null;
        const tiles = tilesInOrder();
        const index = tiles.indexOf(tile);
        if (index < 0) return null;
        const neighbour = tiles[index + direction];
        if (!neighbour || structural.includes(neighbour.entry.type)) return null;
        const left = direction < 0 ? neighbour : tile;
        const right = direction < 0 ? tile : neighbour;
        const gap = tileX(right) - tileX(left) - left.width;
        return Math.abs(gap - itemSpacing) < .5 ? neighbour : null;
    }
    function pressDrag(type, key, x, y) {
        const tiles = tilesInOrder();
        const source = tiles.find(tile => tile.instanceKey === key);
        const remaining = entries.filter(item => item.key !== key && !item.locked);
        drag = {type, key, start: Qt.point(x, y), width: source?.width ?? 140,
            preview: source?.presenter ?? null,
            targets: tiles.filter(tile => tile.instanceKey !== key && !tile.locked).map(tile => ({
                index: remaining.findIndex(item => item.key === tile.instanceKey),
                x: tile.mapToItem(strip, tile.width / 2, 0).x
            }))};
        pointer = Qt.point(x, y);
        dragging = false;
        hoverOnBar = false;
        hoverOnCatalog = false;
    }
    function cancelDrag() { drag = null; dragging = false; hoverOnBar = false; hoverOnCatalog = false; }
    function moveDrag(x, y) {
        if (!drag) return;
        pointer = Qt.point(x, y);
        if (Math.hypot(x - drag.start.x, y - drag.start.y) > 6) dragging = true;
        const point = strip.mapFromItem(root, x, y);
        hoverOnBar = dragging && point.x >= 0 && point.x <= strip.width && point.y >= 0 && point.y <= strip.height;
        const catalogPoint = catalogScroll.mapFromItem(root, x, y);
        hoverOnCatalog = dragging && !!drag.key && editing
            && catalogPoint.x >= 0 && catalogPoint.x <= catalogScroll.width
            && catalogPoint.y >= 0 && catalogPoint.y <= catalogScroll.height;
        if (!hoverOnBar) return;
        // Use list indices rather than just visible tiles so hidden devices keep
        // their place when dropped beside a visible module.
        const remaining = entries.filter(item => item.key !== drag.key && !item.locked);
        if (point.x < 12) { hoverIndex = 0; return; }
        if (point.x > strip.width - 12) { hoverIndex = remaining.length; return; }
        hoverIndex = remaining.length;
        for (const target of drag.targets) {
            if (point.x < target.x) {
                hoverIndex = target.index;
                break;
            }
        }
    }
    onEditingChanged: if (!editing) cancelDrag()
    function releaseDrag() {
        if (!drag) return;
        if (dragging && hoverOnCatalog) BarLayout.remove(drag.key);
        else if (dragging && hoverOnBar) BarLayout.drop(drag.type, drag.key, hoverIndex);
        else if (!dragging) {
            if (drag.key) BarLayout.selectedKey = drag.key;
            else BarLayout.drop(drag.type, "", BarLayout.draft.items.length);
        }
        cancelDrag();
    }
    PanelSurface {
        x: root.outerMargin
        width: parent.width - root.outerMargin * 2
        height: root.barHeight - root.outerMargin * 2
        anchors.verticalCenter: strip.verticalCenter
        color: Config.options.bar.showBackground ? Appearance.colors.colLayer0 : "transparent"
        radius: Config.options.bar.cornerStyle === 1 ? Math.min(width, height) / 2 : 0
        border.width: Config.options.bar.cornerStyle === 1 ? 1 : 0
    }
    Item {
        id: strip
        objectName: "bar-free-strip"
        x: Appearance.sizes.barModuleInset + root.outerMargin
        width: Math.max(0, parent.width - x * 2)
        height: root.barHeight
        y: Config.options.bar.bottom ? root.height - height : 0
        readonly property real gap: 4
        // These are clipping viewports, not user-managed zones. Their boundary
        // follows the pinned module, whose midpoint never moves off the screen center.
        BarLayoutFlow {
            editor: root
            id: before
            objectName: "bar-free-before"
            x: 0
            width: root.anchorIndex >= 0 ? Math.max(0, anchorTile.x - strip.gap) : strip.width
            entries: root.anchorIndex >= 0 ? root.displayEntries.slice(0, root.anchorIndex) : root.displayEntries
            alignEnd: root.anchorIndex >= 0
        }
        BarLayoutTile {
            editor: root
            id: anchorTile
            objectName: "bar-center-tile"
            entry: root.anchorIndex >= 0 ? root.displayEntries[root.anchorIndex] : {key: "", type: "spacer"}
            visible: root.anchorIndex >= 0
            width: Math.min(strip.width, implicitWidth)
            height: strip.height
            x: (strip.width - width) / 2
            Rectangle {
                visible: root.editing
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom
                width: 12; height: 2; radius: 1
                color: Appearance.colors.colPrimary
            }
        }
        BarLayoutFlow {
            editor: root
            id: after
            objectName: "bar-free-after"
            visible: root.anchorIndex >= 0
            x: anchorTile.x + anchorTile.width + strip.gap
            width: Math.max(0, strip.width - x)
            entries: root.anchorIndex >= 0 ? root.displayEntries.slice(root.anchorIndex + 1) : []
        }
        StyledText {
            anchors.centerIn: parent
            visible: root.editing && root.entries.length === 0
            text: Translation.tr("Drag panels here")
            font.pixelSize: Appearance.font.pixelSize.small
            color: Appearance.colors.colSubtext
        }
    }
    PanelSurface {
        id:drawer
        objectName:"bar-editor-drawer"
        visible:root.editing
        x:Math.max(Appearance.sizes.elevationMargin,(parent.width-width)/2)
        y:Config.options.bar.bottom?Appearance.sizes.elevationMargin*2-Appearance.sizes.hyprlandGapsOut:root.barHeight+Appearance.sizes.hyprlandGapsOut
        width:Math.max(1,Math.min(1100,parent.width-Appearance.sizes.elevationMargin*2));height:root.drawerHeight
        radius:Appearance.rounding.large
        ColumnLayout {
            anchors.fill:parent;anchors.margins:16;spacing:10
            RowLayout {
                Layout.fillWidth:true
                StyledText {Layout.fillWidth:true;Layout.minimumWidth:0;text:root.hoverOnCatalog?Translation.tr("Drop here to remove from the bar"):Translation.tr("Edit bar");elide:Text.ElideRight;color:root.hoverOnCatalog?Appearance.colors.colPrimary:Appearance.colors.colOnLayer0;font.weight:Font.DemiBold;font.pixelSize:Appearance.font.pixelSize.large}
                RippleButtonWithIcon{materialIcon:"restart_alt";mainText:Translation.tr("Reset");onClicked:BarLayout.resetDraft()}
                RippleButtonWithIcon{materialIcon:"close";mainText:Translation.tr("Cancel");onClicked:BarLayout.cancel()}
                RippleButtonWithIcon{materialIcon:"check";mainText:Translation.tr("Save");onClicked:BarLayout.save()}
            }
            StyledText {Layout.fillWidth:true;text:Translation.tr("Arrange panels freely. Add flexible spaces to distribute room, or pin one panel to the exact screen center. Scroll when space is limited.");wrapMode:Text.WordWrap;color:Appearance.colors.colSubtext;font.pixelSize:Appearance.font.pixelSize.small}
            RowLayout {
                Layout.fillWidth:true
                StyledText {Layout.fillWidth:true;Layout.minimumWidth:0;text:BarLayout.selected?BarLayout.info(BarLayout.selected.type).name:Translation.tr("Select a panel to move or remove");elide:Text.ElideRight;color:Appearance.colors.colSubtext;font.pixelSize:Appearance.font.pixelSize.small}
                RippleButtonWithIcon {
                    objectName:"bar-pin-center"
                    materialIcon:"center_focus_strong";mainText:Translation.tr("Center on screen")
                    enabled:BarLayout.canCenter(BarLayout.selected)
                    toggled:!!BarLayout.selectedKey&&BarLayout.draft.centerKey===BarLayout.selectedKey
                    onClicked:BarLayout.setCenter(toggled?"":BarLayout.selectedKey)
                }
                MaterialTextField {
                    objectName:"bar-space-size"
                    Layout.preferredWidth:80
                    visible:BarLayout.selected?.type==="spacer"
                    text:String(BarLayout.selected?.size??24)
                    validator:IntValidator {bottom:4;top:600}
                    onEditingFinished:if(acceptableInput)BarLayout.resizeSpacer(BarLayout.selectedKey,Number(text))
                }
                StyledText {visible:BarLayout.selected?.type==="spacer";text:"px · 4–600";font.pixelSize:Appearance.font.pixelSize.small}
                RippleButtonWithIcon{materialIcon:"chevron_left";mainText:"";enabled:!!BarLayout.selectedKey;Accessible.name:Translation.tr("Move selected panel left");onClicked:BarLayout.moveBy(BarLayout.selectedKey,-1)}
                RippleButtonWithIcon{materialIcon:"chevron_right";mainText:"";enabled:!!BarLayout.selectedKey;Accessible.name:Translation.tr("Move selected panel right");onClicked:BarLayout.moveBy(BarLayout.selectedKey,1)}
                RippleButtonWithIcon{materialIcon:"delete";mainText:Translation.tr("Remove");enabled:!!BarLayout.selectedKey;onClicked:BarLayout.remove(BarLayout.selectedKey)}
            }
            Rectangle {
                Layout.fillWidth:true;Layout.fillHeight:true
                radius:Appearance.rounding.small
                color:root.hoverOnCatalog?Appearance.colors.colLayer1Hover:"transparent"
                border.width:root.hoverOnCatalog?1:0
                border.color:Appearance.colors.colPrimary
                Flickable {
                    id:catalogScroll
                    objectName:"bar-module-catalog"
                    anchors.fill:parent
                    contentWidth:width;contentHeight:catalogFlow.implicitHeight
                    clip:true;interactive:!root.drag
                    Flow {
                        id:catalogFlow;width:parent.width;spacing:8
                        Repeater {
                            model:BarLayout.catalog
                            delegate:Rectangle {
                                id:catalogTile
                                required property var modelData
                                readonly property bool available:BarLayout.available(modelData.type)
                                width:Math.min(230,catalogFlow.width);height:42
                                radius:Appearance.rounding.small;color:Appearance.colors.colLayer1
                                opacity:available?1:0.4
                                RowLayout {anchors.fill:parent;anchors.margins:8;MaterialSymbol{text:catalogTile.modelData.icon;iconSize:20;color:Appearance.colors.colPrimary}StyledText{Layout.fillWidth:true;text:catalogTile.modelData.name;elide:Text.ElideRight;font.pixelSize:Appearance.font.pixelSize.small}}
                                BarEditHandle{anchors.fill:parent;enabled:catalogTile.available;editor:root;widgetType:catalogTile.modelData.type}
                            }
                        }
                    }
                }
            }
        }
    }
    Loader {
        id: catalogPreview
        active: !!root.drag && !root.drag.key
        visible: root.dragging
        x: -width - Appearance.sizes.elevationMargin
        sourceComponent: BarWidget {
            widgetType: root.drag?.type ?? ""
            compact: root.compact
            editing: true
            width: implicitWidth
            height: root.barHeight
        }
    }
    ShaderEffectSource {
        objectName: "bar-drag-preview"
        visible: root.dragging
        sourceItem: root.drag?.preview ?? catalogPreview.item
        live: false
        hideSource: root.dragging
        sourceRect: Qt.rect(0, 0, root.dragWidth, root.barHeight)
        width: root.dragWidth
        height: root.barHeight
        x: Math.max(0, Math.min(root.width - width, root.pointer.x - width / 2))
        y: Math.max(0, Math.min(root.height - height, root.pointer.y - height / 2))
        opacity: .6
        z: 50
        onSourceItemChanged: if (sourceItem) scheduleUpdate()
    }
}
