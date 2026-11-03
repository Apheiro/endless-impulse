pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Hyprland
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets

Item {
    id:root
    objectName:"bar-content"
    readonly property var screen:root.QsWindow.window?.screen
    readonly property bool editing:BarLayout.editing&&BarLayout.screenName===screen?.name
    readonly property bool customized:BarLayout.customizedFor(screen?.name ?? "")
    readonly property bool layoutEditing:BarLayout.editing&&(!Config.options.bar.independentLayouts||root.editing)
    readonly property bool contextOpen:context.visible
    readonly property var editorSurface:editing?(configured.item?.editorSurface??null):null
    readonly property var contextSurface:context.visible?contextBackground:null
    implicitHeight:editing?(configured.item?.implicitHeight??Appearance.sizes.barHeight):Appearance.sizes.barHeight+(context.visible?context.height+Appearance.sizes.hyprlandGapsOut:0)
    property real contextX:0
    function openContext(x){if(editing)return;contextX=x;context.visible=true;root.forceActiveFocus();}
    MouseArea {
        width:parent.width;height:Appearance.sizes.barHeight;y:Config.options.bar.bottom?parent.height-height:0;acceptedButtons:Qt.RightButton
        onPressed:mouse=>root.openContext(mouse.x)
    }
    Loader {
        id:legacy
        objectName:"bar-legacy-strip"
        width:parent.width;height:Appearance.sizes.barHeight;y:Config.options.bar.bottom?parent.height-height:0;active:!root.customized&&!root.layoutEditing
        sourceComponent:LegacyBarContent{}
    }
    Loader {
        id:configured
        width:parent.width;height:root.editing?parent.height:Appearance.sizes.barHeight;y:Config.options.bar.bottom?parent.height-height:0;active:root.customized||root.layoutEditing
        sourceComponent:ConfiguredBarContent{editing:root.editing;screenName:root.screen?.name??""}
    }
    Connections {
        target:BarLayout
        function onEditingChanged(){
            if(root.editing)Qt.callLater(()=>{context.visible=false;root.forceActiveFocus();});
        }
        function onScreenNameChanged(){if(root.editing)Qt.callLater(()=>root.forceActiveFocus());}
    }
    Keys.onEscapePressed:{context.visible=false;BarLayout.cancel();}
    Keys.onReturnPressed:if(editing&&!configured.item?.drag)BarLayout.save()
    Keys.onDeletePressed:if(editing)BarLayout.remove(BarLayout.selectedKey)
    Item {
        id:context
        visible:false
        z:100
        width:250+Appearance.sizes.elevationMargin*2
        height:contextItems.implicitHeight+20+Appearance.sizes.elevationMargin*2
        x:Math.max(0,Math.min(root.width-width,root.contextX-Appearance.sizes.elevationMargin))
        y:Config.options.bar.bottom?Appearance.sizes.elevationMargin:Appearance.sizes.barHeight+Appearance.sizes.hyprlandGapsOut-Appearance.sizes.elevationMargin
        PanelSurface{id:contextBackground;anchors.fill:parent;anchors.margins:Appearance.sizes.elevationMargin;radius:Appearance.rounding.large}
        ColumnLayout {
            id:contextItems;anchors{left:parent.left;right:parent.right;top:parent.top;margins:Appearance.sizes.elevationMargin+10}
            RippleButtonWithIcon{objectName:"bar-context-edit";Layout.fillWidth:true;hoverEnabled:true;materialIcon:"edit";mainText:Translation.tr("Edit bar");onClicked:BarLayout.begin(root.screen?.name)}
            RippleButtonWithIcon{Layout.fillWidth:true;materialIcon:"settings";mainText:Translation.tr("Bar settings");onClicked:{context.visible=false;SettingsNavigation.open("BarConfig.qml");}}
        }
        Connections { target: GlobalFocusGrab; function onDismissed() { context.visible=false; } }
    }
}
