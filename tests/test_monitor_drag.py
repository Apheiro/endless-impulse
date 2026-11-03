"""Monitor collisions use logical bounds and continuous movement, not just endpoints."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "src/quickshell"


class MonitorGeometryTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node is needed for pure geometry checks")
    def test_sweeps_sliding_corners_and_multiple_obstacles(self):
        source = (SOURCE / "modules/settings/MonitorGeometry.js").read_text().replace(".pragma library", "")
        result = subprocess.run(["node"], input=source + '''
const assert = require('node:assert/strict');
const tile = {x:0,y:0,width:100,height:100};
const right = {x:100,y:0,width:100,height:100};
assert.deepEqual(move(tile,{x:1000,y:0},[right]),{x:0,y:0});
assert.deepEqual(move(tile,{x:-1000,y:0},[{x:-100,y:0,width:100,height:100}]),{x:0,y:0});
assert.deepEqual(move(tile,{x:0,y:1000},[{x:0,y:100,width:100,height:100}]),{x:0,y:0});
assert.deepEqual(move(tile,{x:0,y:-1000},[{x:0,y:-100,width:100,height:100}]),{x:0,y:0});
assert.deepEqual(move(tile,{x:1000,y:40},[right]),{x:0,y:40});
assert.deepEqual(move(tile,{x:1000,y:1000},[{x:200,y:200,width:100,height:100}]),{x:100,y:100});
assert.deepEqual(move(tile,{x:1000,y:1000},[right,{x:0,y:200,width:100,height:100}]),{x:0,y:100});
assert.deepEqual(move(tile,{x:-100,y:0},[right]),{x:-100,y:0});
// A monitor can be moved around a neighbour, but cannot pass through it.
const below = move(tile,{x:0,y:101},[right]);
assert.deepEqual(move({...tile,...below},{x:250,y:101},[right]),{x:250,y:101});
// Portrait + fractional scale use their actual logical dimensions.
const portrait = {x:-864,y:-40,width:864,height:1536};
const landscape = {x:0,y:0,width:2048,height:1152};
const collision = move(portrait,{x:4000,y:20},[landscape]);
assert.equal(collision.x,-864);
assert(!overlaps({...portrait,...collision},landscape));
''', capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(os.environ.get("WAYLAND_DISPLAY"), "Monitor diagram needs Wayland")
    def test_real_pointer_slides_without_overlap_and_updates_only_draft_on_release(self):
        with tempfile.TemporaryDirectory(prefix="ai-monitor-drag-") as directory:
            base = Path(directory)
            for name in ("modules", "assets", "scripts", "defaults", "translations", "GlobalStates.qml"):
                (base / name).symlink_to(SOURCE / name)
            (base / "services").mkdir()
            for path in (SOURCE / "services").iterdir():
                if path.name != "DesktopSettings.qml": (base / "services" / path.name).symlink_to(path)
            (base / "services/DesktopSettings.qml").write_text('''pragma Singleton
import QtQuick
import Quickshell
Singleton {
    property bool loaded: true
    property bool busy: false
    property var transaction: null
    property var saved: ({monitors:{}})
    property var draft: ({})
    property int writes: 0
    property var monitors: [
        {name:"TEST-A",description:"A",disabled:false,current:{mode:"1920x1080@60Hz",x:0,y:0,scale:1,transform:0}},
        {name:"TEST-B",description:"B",disabled:false,current:{mode:"1920x1080@60Hz",x:1920,y:0,scale:1,transform:0}}
    ]
    function refresh() {}
    function monitor(name) { return draft[name] ?? monitors.find(item=>item.name===name).current; }
    function putMonitor(name, changes) { draft=Object.assign({},draft,{[name]:Object.assign({},monitor(name),changes)}); writes++; }
}
''')
            (base / "shell.qml").write_text('''//@ pragma UseQApplication
import QtQuick
import QtTest
import Quickshell
import Quickshell.Wayland
import qs.services
import qs.modules.settings
ShellRoot {
    id: root
    property int phase: 0
    property point start
    function expect(value,message) { if(!value)throw new Error(message); }
    function find(item,name) {
        if(item.objectName===name)return item;
        for(const child of item.children??[]){const result=find(child,name);if(result)return result;}
        return null;
    }
    TestCase { id:mouse;parent:host.contentItem;name:"MonitorDrag";when:false }
    PanelWindow {
        id:host;implicitWidth:900;implicitHeight:700;exclusiveZone:0
        WlrLayershell.namespace:"quickshell:monitor-drag-test"
        WlrLayershell.keyboardFocus:WlrKeyboardFocus.None
        mask:Region{}
        MonitorsConfig { id:page;anchors.fill:parent }
    }
    Timer {
        interval:250;running:true;repeat:true
        onTriggered:{try{
            const canvas=root.find(page,"monitor-arrangement-canvas");
            const tile=root.find(page,"monitor-tile-TEST-A");
            const handle=root.find(page,"monitor-drag-TEST-A");
            if(root.phase===0){
                root.start=handle.mapToItem(canvas,handle.width/2,handle.height/2);
                mouse.mousePress(handle,handle.width/2,handle.height/2,Qt.LeftButton);
                mouse.mouseMove(canvas,root.start.x+100,root.start.y+30,30);
                root.phase++;return;
            }
            if(root.phase===1){
                root.expect(page.draggingMonitor&&!page.interactive,"page stole the monitor drag");
                root.expect(Math.abs(tile.offsetX)<.1&&tile.offsetY>10,"tile crossed the adjacent monitor or could not slide");
                root.expect(DesktopSettings.writes===0,"drag wrote draft before release");
                mouse.mouseRelease(canvas,root.start.x+100,root.start.y+30,Qt.LeftButton);
                root.phase++;return;
            }
            const spec=DesktopSettings.monitor("TEST-A");
            root.expect(spec.x===0&&spec.y>0&&DesktopSettings.writes===1,"collision was lost on release");
            root.expect(!page.draggingMonitor&&page.interactive,"page stayed locked after drag");
            console.log("MONITOR_DRAG_OK");Qt.quit();
        }catch(error){console.error("MONITOR_DRAG_FAILED",error);Qt.quit();}}
    }
    Timer{interval:8000;running:true;onTriggered:{console.error("MONITOR_DRAG_FAILED timeout");Qt.quit();}}
}
''')
            env = dict(os.environ, DOTS_SHELL_SOURCE=str(base), XDG_CONFIG_HOME=str(base / "config"),
                       XDG_STATE_HOME=str(base / "state"), XDG_CACHE_HOME=str(base / "cache"))
            launcher = env.get("DOTS_TEST_LAUNCHER")
            command = [launcher] if launcher else [shutil.which("quickshell"), "-p", str(base)]
            result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=14)
            logs = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, logs)
            self.assertIn("MONITOR_DRAG_OK", logs)
            for error in ("MONITOR_DRAG_FAILED", "TypeError:", "ReferenceError:", "Binding loop", "Unable to assign"):
                self.assertNotIn(error, logs)
