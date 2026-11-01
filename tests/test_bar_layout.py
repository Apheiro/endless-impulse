"""Live bar editing with isolated preferences and real widget/rendering components."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'src/quickshell'

@unittest.skipUnless(os.environ.get('WAYLAND_DISPLAY'),'Bar editor needs Wayland')
class BarLayoutTests(unittest.TestCase):
    def test_free_layout_spaces_anchor_migration_save_cancel(self):
        self.check_layout(real_focus=False)

    def test_context_menu_hands_focus_to_editor(self):
        self.check_layout(real_focus=True)

    def check_layout(self, real_focus):
        with tempfile.TemporaryDirectory(prefix='ai-bar-layout-') as temporary:
            base=Path(temporary)
            for name in ('modules','assets','scripts','defaults','translations','GlobalStates.qml'):(base/name).symlink_to(SOURCE/name)
            (base/'services').mkdir()
            for entry in (SOURCE/'services').iterdir():
                if entry.name=='GlobalFocusGrab.qml' and not real_focus:
                    (base/'services'/entry.name).write_text(entry.read_text().replace('active: root.dismissable.length > 0','active: false'))
                else:(base/'services'/entry.name).symlink_to(entry)
            (base/'shell.qml').write_text('''//@ pragma UseQApplication
import QtQuick
import QtTest
import Quickshell
import Quickshell.Wayland
import qs.services
import qs.modules.shared
import qs.modules.desktop.bar
ShellRoot {
 id:root
 property int phase:0
 property var editor:null
 property string saved:""
 property var liveFrame:null
 property var menuOwner:null
 property int livePhase:0
 TestCase { id:pointer;parent:host.contentItem;name:"BarPointer";when:false }
 Component.onCompleted:{Config.options.bar.autoHide.enable=true;Config.options.bar.autoHide.pushWindows=false;}
 function expect(condition,message){if(!condition)throw new Error(message);}
 function find(item,name){if(!item)return null;if(item.objectName===name)return item;for(const child of [...(item.children||[]),...(item.resources||[])]){const result=find(child,name);if(result)return result;}if(item.contentItem&&!Array.from(item.children||[]).includes(item.contentItem))return find(item.contentItem,name);return null;}
 function collect(item,name){if(!item)return [];let result=item.objectName===name?[item]:[];for(const child of [...(item.children||[]),...(item.resources||[])])result=result.concat(collect(child,name));return result;}

 Bar {}
 PanelWindow {
  id:host;implicitWidth:1400;implicitHeight:bar.implicitHeight;exclusiveZone:0
  WlrLayershell.namespace:"quickshell:bar-layout-test";WlrLayershell.keyboardFocus:WlrKeyboardFocus.None
  mask:Region{}
  BarContent{id:bar;anchors.fill:parent}
 }
 Timer {
  interval:200;running:true;repeat:true
  onTriggered:{try{
   if(!Config.ready)return;
   if(root.phase===0){
    root.expect(Config.options.bar.layout===null,"initialization saved a layout");
    root.liveFrame=GlobalFocusGrab.persistent.find(window=>window.screen.name===host.screen.name);
    root.expect(root.liveFrame!==undefined,"bar monitor variant was not created");
    root.menuOwner=root.find(root.liveFrame.contentItem,"bar-content");
    root.menuOwner.openContext(200);
    root.expect(root.menuOwner.contextOpen&&!bar.editing,"context menu entered editing without confirmation");
    root.expect(root.liveFrame.mask.regions.some(region=>region.item===root.menuOwner.contextSurface),"menu surface is outside the bar input mask");
    root.phase=-1;return;
   }
   if(root.phase===-1){
    if(root.liveFrame.height<root.menuOwner.implicitHeight&&root.livePhase++<8)return;
    const strip=root.find(root.menuOwner,"bar-legacy-strip");
    root.expect(strip.height===Appearance.sizes.barHeight&&strip.y===0,"opening menu resized or displaced the visible bar");
    const edit=root.find(root.menuOwner,"bar-context-edit");
    root.expect(edit.width>0&&edit.height>0,"edit button has no pointer area");
    pointer.mouseMove(edit,edit.width/2,edit.height/2);
    root.expect(edit.hovered,"edit button does not receive hover");
    pointer.mouseClick(edit,edit.width/2,edit.height/2,Qt.LeftButton);
    root.expect(bar.editing,"context Edit action failed");
    root.livePhase=0;root.phase=1;return;
   }
   if(root.phase===1){
    if(root.menuOwner.contextOpen&&root.livePhase++<8)return;
    root.expect(!root.menuOwner.contextOpen,"context menu stayed open after entering the editor");
    if((root.liveFrame.height<Appearance.sizes.barHeight+100||host.height<Appearance.sizes.barHeight+100)&&root.livePhase++<8)return;
    root.expect(root.liveFrame.height>Appearance.sizes.barHeight+100,"real bar did not grow for the drawer: "+root.liveFrame.height+"/"+root.liveFrame.implicitHeight+" monitor "+root.liveFrame.screen.name+" requested "+BarLayout.screenName+" content "+root.find(root.liveFrame.contentItem,"configured-bar-content")?.editing);
    root.expect(GlobalFocusGrab.dismissable.includes(root.liveFrame),"editor was not registered for outside dismissal");
    const liveDrawer=root.find(root.liveFrame.contentItem,"bar-editor-drawer");
    root.expect(liveDrawer&&root.liveFrame.mask.regions.some(region=>region.item===liveDrawer),"drawer is outside the bar input mask");
    root.editor=root.find(bar,"configured-bar-content");
    root.expect(root.editor&&bar.editing,"editor did not open on its monitor");
    const drawer=root.find(bar,"bar-editor-drawer");
    root.expect(drawer.visible&&host.height>Appearance.sizes.barHeight,"catalog did not unfold");
    const preview=root.find(root.editor,"bar-presenter-workspaces");
    root.expect(preview.previewItem&&preview.previewItem.visible&&preview.previewItem.enabled,"real workspace preview is unavailable or disabled");
    root.expect(preview.implicitWidth===Math.min(preview.moduleItem.contentWidthLimit,preview.previewItem.implicitWidth)+preview.moduleItem.horizontalPadding*2,"workspace preview does not preserve its natural width");
    const handle=root.find(root.editor,"bar-edit-handle-clock");
    pointer.mouseMove(handle,5,12);
    root.expect(root.find(handle,"bar-edit-tooltip").internalVisibleCondition,"hovered panel has no tooltip");
    root.expect(root.collect(root.editor,"bar-edit-tooltip").filter(tip=>tip.internalVisibleCondition).length===1,"multiple editor tooltips are enabled");
    root.expect(root.collect(root.editor,"bar-panel-selection").every(outline=>!outline.visible),"unselected panels have an outline");
    pointer.mouseClick(handle,5,12,Qt.LeftButton);
    root.expect(BarLayout.selectedKey==="clock"&&!root.editor.drag,"real panel handle did not select without activating its controls");
    pointer.mouseMove(root.editor,drawer.x+5,drawer.y+5);
    root.expect(root.collect(root.editor,"bar-edit-tooltip").every(tip=>!tip.internalVisibleCondition),"tooltips remain enabled without hover");
    const strip=root.find(root.editor,"bar-free-strip");const target=strip.mapToItem(root.editor,1,strip.height/2);
    root.editor.pressDrag("workspaces","workspaces",500,20);root.editor.moveDrag(target.x,target.y);root.editor.releaseDrag();
    root.expect(BarLayout.draft.items[0].key==="workspaces","free row drag failed");
    root.phase++;return;
   }
   if(root.phase===2){
    root.expect(!BarLayout.drop("workspaces","",0),"duplicate singleton accepted");
    root.expect(!BarLayout.drop("unknown","",0),"unknown widget accepted");
    BarLayout.drop("separator","",0);BarLayout.drop("separator","",0);
    root.expect(BarLayout.draft.items.filter(item=>item.type==="separator").length===2,"repeated separators rejected");
    const item=BarLayout.draft.items[0];BarLayout.moveBy(item.key,1);
    root.expect(BarLayout.draft.items[1].key===item.key,"free reordering failed");
    BarLayout.drop("spacer","",0);const gap=BarLayout.selectedKey;
    const sizeField=root.find(root.editor,"bar-space-size");sizeField.text="123";sizeField.editingFinished();
    root.expect(BarLayout.locate(gap).item.size===123,"fixed space width field failed");
    BarLayout.resizeSpacer(gap,99999);root.expect(BarLayout.locate(gap).item.size===600,"space limit ignored");
    BarLayout.setCenter(gap);root.expect(BarLayout.draft.centerKey!==gap,"spacing can be anchored");
    BarLayout.selectedKey="clock";const pin=root.find(root.editor,"bar-pin-center");
    pin.click();root.expect(BarLayout.draft.centerKey==="","pin button did not disable centering");
    pin.click();
    root.expect(BarLayout.draft.centerKey==="clock","center anchor was not saved in draft");
    for(const type of ["networkSpeed","search","power","profile","keyboard","recording","updates"]){root.expect(BarLayout.drop(type,"",0),"catalog item unavailable "+type);}
    root.phase++;return;
   }
   if(root.phase===3){
    root.expect(Config.options.bar.layout===null,"draft edits leaked before save");
    BarLayout.save();root.saved=JSON.stringify(Config.options.bar.layout);
    root.expect(!bar.editing&&BarLayout.customized,"save did not activate modular layout");
    host.implicitWidth=760;root.phase++;return;
   }
   if(root.phase===4){
    const strip=root.find(root.editor,"bar-free-strip");const anchor=root.find(root.editor,"bar-center-tile");
    const before=root.find(root.editor,"bar-free-before"),after=root.find(root.editor,"bar-free-after");
    root.expect(Math.abs(anchor.x+anchor.width/2-strip.width/2)<.1,"asymmetric content displaced the exact center");
    root.expect(before.width>=0&&after.width>=0&&before.x+before.width<=anchor.x&&after.x>=anchor.x+anchor.width,"content overlaps the anchor on a narrow screen");
    root.expect(before.contentWidth>before.width,"overflow has no horizontal scroll range");
    BarLayout.begin(host.screen.name);const first=BarLayout.draft.items[0].key;BarLayout.remove(first);BarLayout.cancel();
    root.expect(JSON.stringify(Config.options.bar.layout)===root.saved,"cancel changed the saved layout");
    root.expect(BarLayout.saved.items.some(item=>item.key===first),"cancel lost a widget");
    const clean=BarLayout.normalize({version:2,items:[{key:"same",type:"clock"},{key:"same",type:"media"},{key:"second",type:"clock"}],centerKey:"same"});
    root.expect(clean.items.length===1&&clean.centerKey==="same","malformed layout was not normalized");
    const migrated=BarLayout.normalize({left:[{key:"title",type:"activeWindow"}],center:[{key:"old-clock",type:"clock"}],right:[{key:"tray",type:"tray"}]});
    root.expect(migrated.items.map(item=>item.type).join(",")==="activeWindow,flex,clock,flex,tray"&&migrated.centerKey==="old-clock","legacy layout migration lost ordering or clock anchor");
    BarLayout.draft={version:2,items:[{key:"left",type:"search"},{key:"flex-a",type:"flex"},{key:"flex-b",type:"flex"},{key:"right",type:"power"}],centerKey:""};
    BarLayout.editing=true;root.phase=5;return;
   }
   if(root.phase===5){
    const strip=root.find(root.editor,"bar-free-strip");
    const tiles=root.editor.tilesInOrder();
    const a=tiles.find(tile=>tile.instanceKey==="flex-a"),b=tiles.find(tile=>tile.instanceKey==="flex-b");
    root.expect(a&&b&&a.width>32&&Math.abs(a.width-b.width)<1,"flexible spaces do not share surplus width equally");
    root.expect(tiles[0].x===0&&Math.abs(tiles[tiles.length-1].x+tiles[tiles.length-1].width-strip.width)<1,"free layout did not fill its row");
    BarLayout.save();root.phase=6;return;
   }
   if(root.phase===6){
    const strip=root.find(root.editor,"bar-free-strip"),tiles=root.editor.tilesInOrder();
    const a=tiles.find(tile=>tile.instanceKey==="flex-a"),b=tiles.find(tile=>tile.instanceKey==="flex-b");
    root.expect(a.width>0&&Math.abs(a.width-b.width)<1,"flexible spaces collapse outside edit mode");
    root.expect(Math.abs(tiles[tiles.length-1].x+tiles[tiles.length-1].width-strip.width)<1,"normal row does not fill its available width");
    BarLayout.begin(host.screen.name);
    BarLayout.setCenter("right");BarLayout.remove("right");root.expect(BarLayout.draft.centerKey==="","removing the anchor left a stale pin");
    BarLayout.setCenter("");root.expect(BarLayout.draft.centerKey==="","centering cannot be disabled");
    BarLayout.cancel();
    BarLayout.restoreSaved();root.phase++;return;
   }
   root.expect(!BarLayout.customized&&Config.options.bar.layout===null,"original layout was not restored");
   console.log("BAR_LAYOUT_OK");Qt.quit();
  }catch(error){console.error("BAR_LAYOUT_FAILED",error,error.stack);Qt.quit();}}
 }
 Timer{interval:12000;running:true;onTriggered:{console.error("BAR_LAYOUT_FAILED timeout");Qt.quit();}}
}''')
            env=dict(os.environ,DOTS_SHELL_SOURCE=str(base),XDG_CONFIG_HOME=str(base/'config'),XDG_STATE_HOME=str(base/'state'),XDG_CACHE_HOME=str(base/'cache'))
            launcher=env.get('DOTS_TEST_LAUNCHER')
            result=subprocess.run([launcher] if launcher else [shutil.which('quickshell'),'-p',str(base)],env=env,capture_output=True,text=True,timeout=16)
            logs=result.stdout+result.stderr
            self.assertEqual(result.returncode,0,logs);self.assertIn('BAR_LAYOUT_OK',logs)
            for error in ('BAR_LAYOUT_FAILED','TypeError:','ReferenceError:','Cannot assign','Binding loop','Unable to assign'):
                self.assertNotIn(error,logs)
