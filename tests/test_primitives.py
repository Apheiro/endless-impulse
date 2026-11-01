"""Compile migrated foundations and verify the bar's shared visual contract."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/quickshell'


@unittest.skipUnless(os.environ.get('WAYLAND_DISPLAY'), 'QML foundations need Wayland')
class PrimitiveTests(unittest.TestCase):
    def test_type_graph_and_shared_bar_styles(self):
        paths = [str(p.relative_to(SOURCE)) for p in (SOURCE/'modules/shared/primitives').rglob('*.qml')]
        paths += ['shellVariants/DesktopShell.qml', 'shellVariants/WindowsStyleShell.qml']
        with tempfile.TemporaryDirectory(prefix='ai-primitives-') as temporary:
            base = Path(temporary)
            for name in ('modules', 'services', 'assets', 'scripts', 'defaults', 'translations', 'GlobalStates.qml', 'shellVariants'):
                (base/name).symlink_to(SOURCE/name)
            (base/'shell.qml').write_text('''//@ pragma UseQApplication
//@ pragma Env QT_QUICK_CONTROLS_STYLE=Basic
import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Wayland
import qs
import "shellVariants"
import qs.services
import qs.modules.shared
import qs.modules.shared.primitives.common
import qs.modules.desktop.bar
ShellRoot {
 id:root
 property int phase:0
 property int visited:0
 property var types:Object.keys(BarModuleRegistry.sources)
 function expect(condition,message){if(!condition)throw new Error(message);}
 function find(item,name){if(!item)return null;if(item.objectName===name)return item;for(const child of [...(item.children||[]),...(item.resources||[])]){const result=find(child,name);if(result)return result;}return null;}
 PanelWindow {
  id:host;implicitWidth:1200;implicitHeight:80;exclusiveZone:0
  WlrLayershell.namespace:"quickshell:primitive-test"
  WlrLayershell.keyboardFocus:WlrKeyboardFocus.None
  mask:Region{}
  BarWidget{id:module;widgetType:root.types[root.visited]??"";width:implicitWidth;height:Appearance.sizes.barHeight;separatorBefore:true}
 }
 Timer {
  interval:100;running:true;repeat:true
  onTriggered:{try{
   if(!Config.ready)return;
   if(root.phase===0){
    for(const path of __PATHS__){const component=Qt.createComponent(Quickshell.shellPath(path),Component.PreferSynchronous);root.expect(component.status===Component.Ready,path+": "+component.errorString());component.destroy();}
    Config.options.bar.borderless=false;Config.options.bar.showBackground=true;root.phase=1;return;
   }
   if(root.phase===1){
    root.expect(module.moduleItem,"module failed to load: "+module.widgetType);
    if(["separator","spacer","flex"].includes(module.widgetType)){
     root.expect(!root.find(module,"bar-module-surface"),"layout entry has a module surface");root.phase=4;return;
    }
    module.moduleItem.active=false;module.moduleItem.hoverable=false;
    const surface=root.find(module,"bar-module-surface");
    root.expect(surface,"module bypasses shared surface: "+module.widgetType);
    root.expect(Math.abs(surface.radius-Math.min(surface.width,surface.height)/2)<.1,"pill has flat ends: "+module.widgetType);
    root.expect(surface.y>=Appearance.sizes.barModuleInset&&surface.y+surface.height<=module.height-Appearance.sizes.barModuleInset,"surface fills the bar height: "+module.widgetType);
    const content=module.moduleItem.contentItem;
    root.expect(content.x===Appearance.sizes.barModulePadding&&module.width-content.x-content.width===Appearance.sizes.barModulePadding,"module bypasses shared padding: "+module.widgetType);
    let preview=module.previewItem;
    if(preview instanceof Loader)preview=preview.item;
    const layout=preview instanceof RowLayout||preview instanceof ColumnLayout?preview:preview?.children.find(child=>child instanceof RowLayout||child instanceof ColumnLayout);
    if(layout&&module.width>0&&layout.width>0){
     const left=layout.mapToItem(module.moduleItem,0,0).x;
     root.expect(Math.abs(left-Appearance.sizes.barModulePadding)<.1&&Math.abs(module.width-left-layout.width-Appearance.sizes.barModulePadding)<.1,"content adds private padding: "+module.widgetType+" "+left+"/"+(module.width-left-layout.width));
    }
    if(String(surface.color)!==String(Appearance.colors.colLayer1))return;
    root.expect(surface.color.a<1,"normal module surface is opaque: "+module.widgetType);
    Config.options.bar.borderless=true;root.phase=2;return;
   }
   if(root.phase===2){
    const surface=root.find(module,"bar-module-surface");
    if(surface.color.a>.001)return; // Respect theme color transition before inspecting its endpoint.
    root.expect(root.find(module,"bar-module-separator").visible===module.moduleItem.visible,"line style has no separator: "+module.widgetType);
    module.moduleItem.active=true;root.phase=3;return;
   }
   if(root.phase===3){
    const surface=root.find(module,"bar-module-surface");
    if(String(surface.color)!==String(Appearance.colors.colSecondaryContainer))return;
    root.expect(String(module.moduleItem.foreground)===String(Appearance.colors.colOnSecondaryContainer),"active state has unpaired text color");
    root.phase=4;return;
   }
   Config.options.bar.borderless=false;
   root.visited++;
   if(root.visited>=root.types.length){console.log("PRIMITIVES_OK");Qt.quit();return;}
   root.phase=1;
  }catch(error){console.error("PRIMITIVES_FAILED",error,error.stack);Qt.quit();}}
 }
 Timer{interval:30000;running:true;onTriggered:{console.error("PRIMITIVES_FAILED timeout at "+root.types[root.visited]+" phase "+root.phase);Qt.quit();}}
}'''.replace('__PATHS__', json.dumps(paths)))
            env = dict(os.environ, DOTS_SHELL_SOURCE=str(base), XDG_CONFIG_HOME=str(base/'config'), XDG_STATE_HOME=str(base/'state'), XDG_CACHE_HOME=str(base/'cache'))
            launcher = env.get('DOTS_TEST_LAUNCHER')
            command = [launcher] if launcher else [shutil.which('quickshell'), '-p', str(base)]
            result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=35)
            logs = result.stdout+result.stderr
            self.assertEqual(result.returncode, 0, logs)
            self.assertIn('PRIMITIVES_OK', logs)
            for error in ('PRIMITIVES_FAILED', 'TypeError:', 'ReferenceError:', 'Cannot assign', 'Binding loop', 'Unable to assign'):
                self.assertNotIn(error, logs)
