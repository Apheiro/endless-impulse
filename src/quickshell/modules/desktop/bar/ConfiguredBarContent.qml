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
    readonly property real itemSpacing: 4
    readonly property real barHeight: Appearance.sizes.barHeight
    readonly property real outerMargin: Config.options.bar.cornerStyle === 1 ? Appearance.sizes.hyprlandGapsOut : 0
    readonly property var editorSurface: drawer
    readonly property real drawerHeight: Math.min(390, (root.QsWindow.window?.screen?.height ?? 900) * .45)
    implicitHeight: barHeight + (editing ? drawerHeight + Appearance.sizes.elevationMargin * 2 : 0)
    readonly property var entries: {
        const items = BarLayout.layout.items;
        if (ScreenRecorder.active && !items.some(item => ["utilities", "recording"].includes(item.type)))
            return [...items, {key: "__active-recording", type: "recording", locked: true}];
        return items;
    }
    readonly property int anchorIndex: entries.findIndex(item => item.key === BarLayout.layout.centerKey)
    property var drag: null
    property bool dragging: false
    property point pointer: Qt.point(0, 0)
    property bool hoverOnBar: false
    property int hoverIndex: 0

    function dividerBetween(previous, current) {
        const structural = ["spacer", "flex", "separator"];
        return !!previous && !structural.includes(previous.type) && !structural.includes(current.type);
    }
    function tilesInOrder() {
        const tiles = {};
        for (const row of [before.row, after.row]) {
            for (const child of row.children) if (child.instanceKey !== undefined) tiles[child.instanceKey] = child;
        }
        if (anchorIndex >= 0) tiles[anchorTile.instanceKey] = anchorTile;
        return entries.map(item => tiles[item.key]).filter(tile => tile && tile.visible);
    }
    function pressDrag(type, key, x, y) {
        drag = {type, key, start: Qt.point(x, y)};
        pointer = Qt.point(x, y);
        dragging = false;
        hoverOnBar = false;
    }
    function cancelDrag() { drag = null; dragging = false; hoverOnBar = false; }
    function moveDrag(x, y) {
        if (!drag) return;
        pointer = Qt.point(x, y);
        if (Math.hypot(x - drag.start.x, y - drag.start.y) > 6) dragging = true;
        const point = strip.mapFromItem(root, x, y);
        hoverOnBar = dragging && point.x >= 0 && point.x <= strip.width && point.y >= 0 && point.y <= strip.height;
        if (!hoverOnBar) return;
        // Use list indices rather than just visible tiles so hidden devices keep
        // their place when dropped beside a visible module.
        const remaining = entries.filter(item => item.key !== drag.key && !item.locked);
        if (point.x < 12) { hoverIndex = 0; return; }
        if (point.x > strip.width - 12) { hoverIndex = remaining.length; return; }
        hoverIndex = remaining.length;
        for (const tile of tilesInOrder()) {
            if (tile.instanceKey === drag.key || tile.locked) continue;
            if (point.x < tile.mapToItem(strip, tile.width / 2, 0).x) {
                hoverIndex = remaining.findIndex(item => item.key === tile.instanceKey);
                break;
            }
        }
    }
    function releaseDrag() {
        if (!drag) return;
        if (dragging && hoverOnBar) BarLayout.drop(drag.type, drag.key, hoverIndex);
        else if (!dragging) {
            if (drag.key) BarLayout.selectedKey = drag.key;
            else BarLayout.drop(drag.type, "", BarLayout.draft.items.length);
        }
        cancelDrag();
    }
    Rectangle {
        x: root.outerMargin
        width: parent.width - root.outerMargin * 2
        height: root.barHeight - root.outerMargin * 2
        anchors.verticalCenter: strip.verticalCenter
        color: Config.options.bar.showBackground ? Appearance.colors.colLayer0 : "transparent"
        radius: Config.options.bar.cornerStyle === 1 ? Appearance.rounding.windowRounding : 0
        border.width: Config.options.bar.cornerStyle === 1 ? 1 : 0
        border.color: Appearance.colors.colLayer0Border
    }
    Item {
        id: strip
        objectName: "bar-free-strip"
        x: Appearance.sizes.elevationMargin + root.outerMargin
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
            entries: root.anchorIndex >= 0 ? root.entries.slice(0, root.anchorIndex) : root.entries
            alignEnd: root.anchorIndex >= 0
        }
        BarLayoutTile {
            editor: root
            id: anchorTile
            objectName: "bar-center-tile"
            separatorBefore: root.anchorIndex > 0 && root.dividerBetween(root.entries[root.anchorIndex - 1], root.entries[root.anchorIndex])
            entry: root.anchorIndex >= 0 ? root.entries[root.anchorIndex] : {key: "", type: "spacer"}
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
            previousEntry: root.anchorIndex >= 0 ? root.entries[root.anchorIndex] : null
            visible: root.anchorIndex >= 0
            x: anchorTile.x + anchorTile.width + strip.gap
            width: Math.max(0, strip.width - x)
            entries: root.anchorIndex >= 0 ? root.entries.slice(root.anchorIndex + 1) : []
        }
        StyledText {
            anchors.centerIn: parent
            visible: root.editing && root.entries.length === 0
            text: Translation.tr("Drag panels here")
            font.pixelSize: Appearance.font.pixelSize.small
            color: Appearance.colors.colSubtext
        }
        Rectangle {
            visible: root.dragging && root.hoverOnBar
            x: {
                const tiles = root.tilesInOrder().filter(tile => tile.instanceKey !== root.drag?.key && !tile.locked);
                const item = BarLayout.draft.items.filter(entry => entry.key !== root.drag?.key)[root.hoverIndex];
                const tile = tiles.find(tile => tile.instanceKey === item?.key);
                const end = tiles.length ? tiles[tiles.length - 1].mapToItem(strip, tiles[tiles.length - 1].width, 0).x : 0;
                return Math.max(0, Math.min(strip.width - width, tile ? tile.mapToItem(strip, 0, 0).x - width : end));
            }
            y: 4; width: 3; height: strip.height - 8; radius: 1
            color: Appearance.colors.colPrimary
        }
    }
    StyledRectangularShadow {target:drawer;visible:drawer.visible}
    Rectangle {
        id:drawer
        objectName:"bar-editor-drawer"
        visible:root.editing
        x:Math.max(Appearance.sizes.elevationMargin,(parent.width-width)/2)
        y:Config.options.bar.bottom?Appearance.sizes.elevationMargin*2-Appearance.sizes.hyprlandGapsOut:root.barHeight+Appearance.sizes.hyprlandGapsOut
        width:Math.max(1,Math.min(1100,parent.width-Appearance.sizes.elevationMargin*2));height:root.drawerHeight
        radius:Appearance.rounding.large;color:Appearance.colors.colLayer0;border.width:1;border.color:Appearance.colors.colLayer0Border
        ColumnLayout {
            anchors.fill:parent;anchors.margins:16;spacing:10
            RowLayout {
                Layout.fillWidth:true
                StyledText {Layout.fillWidth:true;text:Translation.tr("Edit bar");font.weight:Font.DemiBold;font.pixelSize:Appearance.font.pixelSize.large}
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
            Flickable {
                id:catalogScroll
                Layout.fillWidth:true;Layout.fillHeight:true
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
    Rectangle {
        visible:root.dragging;x:Math.max(0,Math.min(root.width-width,root.pointer.x+12));y:root.pointer.y+12;z:50
        width:ghostLabel.implicitWidth+24;height:34;radius:Appearance.rounding.small
        color:Appearance.colors.colSecondaryContainer;border.width:1;border.color:Appearance.colors.colPrimary
        StyledText{id:ghostLabel;anchors.centerIn:parent;text:root.drag?BarLayout.info(root.drag.type).name:"";color:Appearance.colors.colOnSecondaryContainer;font.pixelSize:Appearance.font.pixelSize.small}
    }
}
