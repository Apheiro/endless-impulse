import qs.modules.shared.primitives.common
import QtQuick
import qs.services
import qs.modules.shared.widgets

MouseArea {
    id:root
    objectName:"bar-edit-handle-"+(widgetKey||widgetType)
    required property var editor
    required property string widgetType
    property string widgetKey:""
    property var scrollTarget:null
    readonly property bool hovered:containsMouse
    acceptedButtons:Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
    hoverEnabled:true
    preventStealing:true
    cursorShape:pressed?Qt.ClosedHandCursor:Qt.OpenHandCursor
    onPressed:mouse=>{if(mouse.button!==Qt.LeftButton)return;const p=mapToItem(editor,mouse.x,mouse.y);editor.pressDrag(widgetType,widgetKey,p.x,p.y);}
    onPositionChanged:mouse=>{if(pressedButtons & Qt.LeftButton){const p=mapToItem(editor,mouse.x,mouse.y);editor.moveDrag(p.x,p.y);}}
    onReleased:mouse=>{if(mouse.button===Qt.LeftButton)editor.releaseDrag();}
    onCanceled:editor.cancelDrag()
    onWheel: event => {
        if (!scrollTarget) { event.accepted=!!widgetKey; return; }
        const delta = event.pixelDelta.x || event.pixelDelta.y || event.angleDelta.x / 3 || event.angleDelta.y / 3;
        scrollTarget.contentX = Math.max(0, Math.min(scrollTarget.contentWidth-scrollTarget.width, scrollTarget.contentX-delta));
        event.accepted=true;
    }
    StyledToolTip {
        objectName:"bar-edit-tooltip"
        text: BarLayout.info(root.widgetType).name
        extraVisibleCondition: root.containsMouse && !root.editor.drag
    }
}
