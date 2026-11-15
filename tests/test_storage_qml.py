"""Real Rust engine + native QML page, synthetic inventory, isolated XDG state."""
import json
import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/quickshell"


class StorageQmlTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("quickshell"), "Quickshell unavailable")
    def test_isolated_page_worker_navigation_and_responsive(self):
        with tempfile.TemporaryDirectory(prefix="ei-storage-") as temporary:
            base = Path(temporary)
            def write(name, text):
                path = base / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            def copy(name): write(name, (SOURCE / name).read_text())
            for name in ("StorageConfig", "SettingsPage", "SettingsSection", "SettingsCatalog"):
                copy("modules/settings/" + name + ".qml")
            copy("services/Storage.qml")
            for path in (SOURCE / "modules/settings/storage").iterdir():
                copy("modules/settings/storage/" + path.name)
            for name in ("SettingsCard", "ContentPage"):
                copy("modules/shared/primitives/settings/" + name + ".qml")
            for name in ("StyledIndeterminateProgressBar", "StyledText", "MaterialSymbol", "MaterialTextField", "RippleButton", "StyledFlickable", "StyledScrollBar", "StyledSwitch", "StyledComboBox", "StyledListView", "StyledRectangularShadow", "PointingHandInteraction", "SegmentedControl"):
                copy("modules/shared/primitives/common/" + name + ".qml")
            # Software offscreen cannot render the Qt5Compat OpacityMask.
            # Disable only that effect in the temporary primitive copy so the
            # native button surface/foreground pairs are visible in captures.
            ripple = base / "modules/shared/primitives/common/RippleButton.qml"
            ripple.write_text(ripple.read_text().replace("layer.enabled: true", "layer.enabled: false"))
            copy("modules/shared/widgets/RippleButtonWithIcon.qml")
            copy("modules/shared/functions/ColorUtils.qml")
            write("services/Translation.qml", 'pragma Singleton\nimport QtQuick\nQtObject { function tr(text) { return text; } }')
            write("modules/shared/Config.qml", 'pragma Singleton\nimport QtQuick\nQtObject { property var options: ({interactions:{scrolling:{touchpadScrollFactor:100,mouseScrollFactor:50,mouseScrollDeltaThreshold:120,fasterTouchpadScroll:false}}}) }')
            appearance = (SOURCE / "modules/shared/Appearance.qml").read_text()
            colors = {key: "#eeeeee" if key.startswith("colOn") else "#aaccff" if key == "colPrimary" else "#bbbbbb" if key == "colSubtext" else "#333333" for key in re.findall(r"property color (col\w+):", appearance)}
            colors.update(colSecondaryContainer="#354254", colOutline="#8190a0", colPrimary="#aaccff", colPrimaryHover="#b9d5ff", colOutlineVariant="#596473")
            if os.environ.get("STORAGE_TEST_LIGHT"):
                colors.update({k: "#222222" for k in colors if k.startswith("colOn")})
                colors.update(colLayer0="#fdfbff", colPrimary="#315f99", colPrimaryHover="#426fa8", colBackgroundSurfaceContainer="#f1f1f7", colSubtext="#555555", colLayer2="#dedee8", colLayer1="#eeeeee", colSecondaryContainer="#d6e1f2")
            if os.environ.get("STORAGE_TEST_COLLISION"):
                colors.update(colSecondaryContainer="#474747", colPrimary="#474747", colPrimaryHover="#474747")
            m3 = dict(re.findall(r'property color (m3\w+): "(#[^"]+)"', appearance), darkmode=True)
            m3.update(m3primaryContainer="#3b628e", m3tertiary="#dab5f5", m3secondary="#95d6be", m3tertiaryContainer="#805a9c", m3secondaryContainer="#477c6c", m3onPrimaryContainer="#eff3ff", m3onSecondary="#142b22", m3onTertiary="#30203b", m3onPrimary="#18283f", darkmode=not bool(os.environ.get("STORAGE_TEST_LIGHT")))
            if os.environ.get("STORAGE_TEST_LIGHT"): m3["m3onPrimary"] = "#ffffff"
            if os.environ.get("STORAGE_TEST_COLLISION"):
                m3.update({key: "#474747" for key in ("m3tertiary", "m3secondary", "m3primaryContainer", "m3tertiaryContainer", "m3secondaryContainer")})
            tokens = dict(colors=colors, m3colors=m3,
                          font=dict(family=dict(main="Sans", numbers="Sans", iconMaterial="Material Symbols Rounded", iconNerd="Sans"), pixelSize=dict(small=14, smaller=12, normal=15, larger=18), variableAxes=dict(main={})),
                          rounding=dict(small=8, normal=12, large=16, full=1000, unsharpenmore=8),
                          sizes=dict(textInputHorizontalPadding=12, textInputVerticalPadding=8, textInputMinimumHeight=40, elevationMargin=16),
                          animationCurves=dict(standardDecel=[0,0,1,1,1,1], expressiveFastSpatialDuration=0, expressiveFastSpatial=[0,0,1,1,1,1]))
            scale = float(os.environ.get("STORAGE_TEST_SCALE", "1"))
            tokens["font"]["pixelSize"] = {k: round(v * scale) for k,v in tokens["font"]["pixelSize"].items()}
            animation = '''property QtObject animation: QtObject {
                property QtObject elementMoveFast: QtObject { id: fast; property int duration: 0; property int type: Easing.Linear; property var bezierCurve: [0,0,1,1,1,1]; property Component colorAnimation: ColorAnimation { duration: 0 }; property Component numberAnimation: NumberAnimation { duration: 0 } }
                property QtObject elementMoveEnter: fast
                property QtObject scroll: fast
            }'''
            write("modules/shared/Appearance.qml", 'pragma Singleton\nimport QtQuick\nQtObject {\n'
                  + ''.join('property var ' + key + ':' + json.dumps(value) + '\n' for key, value in tokens.items())
                  + animation + '\nfunction animationDuration(ms) { return 0; } }')
            # Real worker and service; the inventory is fully synthetic, and the
            # executable emits fixture JSON without traversing any filesystem.
            for folder in ('root', 'root/home', 'root/home/alice', 'root/home/shared', 'boot', 'proton', 'usb'):
                (base / folder).mkdir(parents=True, exist_ok=True)
            records = [dict(mountId='1', device='259:2', root='/', mount=str(base / 'root'), fs='ext4', source='/dev/nvme0n1p2'),
                       dict(mountId='2', device='259:1', root='/', mount=str(base / 'boot'), fs='vfat', source='/dev/nvme0n1p1'),
                       dict(mountId='3', device='0:71', root='/', mount=str(base / 'proton'), fs='fuse.rclone', source='proton:'),
                       dict(mountId='4', device='8:17', root='/', mount=str(base / 'usb'), fs='ext4', source='/dev/sdb1')]
            blocks = {'blockdevices': [
                {'name':'nvme0n1','kname':'nvme0n1','path':'/dev/nvme0n1','maj:min':'259:0','type':'disk','size':1000000,'model':'NVMe System SSD','tran':'nvme','rota':False,'children':[
                    {'name':'nvme0n1p2','kname':'nvme0n1p2','path':'/dev/nvme0n1p2','type':'part','maj:min':'259:2','size':900000,'fstype':'ext4','label':'System'},
                    {'name':'nvme0n1p1','kname':'nvme0n1p1','path':'/dev/nvme0n1p1','type':'part','maj:min':'259:1','size':100000,'fstype':'vfat','label':'Boot'}]},
                {'name':'sda','kname':'sda','path':'/dev/sda','maj:min':'8:0','type':'disk','size':2000000,'model':'WD SATA HDD','tran':'sata','rota':True,'children':[
                    {'name':'sda1','kname':'sda1','path':'/dev/sda1','type':'part','maj:min':'8:1','size':2000000,'fstype':'ext4'}]},
                {'name':'sdb','kname':'sdb','path':'/dev/sdb','maj:min':'8:16','type':'disk','size':300000,'model':'USB removable','tran':'usb','rm':True,'rota':False,'children':[
                    {'name':'sdb1','kname':'sdb1','path':'/dev/sdb1','type':'part','maj:min':'8:17','size':300000,'label':'USB'}]}]}
            write('inventory.json', json.dumps({'records': records, 'blocks': blocks}))
            write('scripts/storage/control.py',
                  'import importlib.util,json\nfrom pathlib import Path\nfrom types import SimpleNamespace\n'
                  + 'spec=importlib.util.spec_from_file_location("engine",'+repr(str(SOURCE / 'scripts/storage/control.py'))+')\n'
                  + 'm=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)\n'
                  + 'data=json.loads(Path('+repr(str(base / 'inventory.json'))+').read_text())\n'
                  + 'm.mounts=lambda: data["records"]\n'
                  + 'discover=m.discover\n'
                  + 'requests=0\n'
                  + 'def inventory():\n global requests\n requests+=1\n if requests>1:\n  data["records"][:]=[r for r in data["records"] if r["device"]!="8:17"]\n  data["blocks"]["blockdevices"][:]=[d for d in data["blocks"]["blockdevices"] if d["name"]!="sdb"]\n return discover(data["records"],data["blocks"],lambda p: SimpleNamespace(f_frsize=1,f_bsize=1,f_blocks=8*1024*1024,f_bfree=3*1024*1024,f_bavail=2*1024*1024))\n'
                  + 'm.discover=inventory\n'
                  + 'm.main()\n')
            # Every scan below uses the compiled Rust engine on this temp tree.
            fixture = base / 'root'
            for name, size in [('home/alice', 1048576), ('home/shared', 65536), ('usr', 262144), ('var', 131072)]:
                folder = fixture / name
                folder.mkdir(parents=True, exist_ok=True)
                (folder / 'data').write_bytes(b'x' * size)
            os.link(fixture / 'home/alice/data', fixture / 'var/hardlink')
            (fixture / 'loop').symlink_to('.')
            with (fixture / 'sparse').open('wb') as stream: stream.truncate(128 * 1024 * 1024)
            for i in range(170): (fixture / ('tiny%03d' % i)).mkdir()
            denied = None
            if os.environ.get('STORAGE_TEST_WARNINGS'):
                denied = fixture / 'home/denied'
                denied.mkdir()
                denied.chmod(0)
            if os.environ.get('STORAGE_TEST_FATAL'):
                fixture = fixture / 'missing'
                records[0]['mount'] = str(fixture)
                write('inventory.json', json.dumps({'records': records, 'blocks': blocks}))
            write("shell.qml", '''//@ pragma UseQApplication
//@ pragma Env QT_QUICK_CONTROLS_STYLE=Basic
import QtQuick
import QtQuick.Window
import QtTest
import Quickshell
import qs.modules.settings
import qs.services
import qs.modules.shared
import "modules/settings/storage/StorageMath.js" as Accounting
ShellRoot {
    id: test
    Window { id: view; visible: true; width: 1250; height: 900; color: "#202020" }
    Rectangle { parent: view.contentItem; anchors.fill: parent; color: Appearance.colors.colLayer0 }
    TestCase { id: pointer; parent: view.contentItem; name: "StoragePointer"; when: false }
    property int phase: 0
    property var page: null
    property string fixture: Quickshell.env("STORAGE_FIXTURE")
    property string home: fixture+"/home"
    property int scanSequence: -1
    property int failedId: -1
    property int errorWait: 0
    property bool loadingCaptured: false
    property bool refreshCaptured: false
    property bool sawLoading: false
    property string nativeSnapshot: ""
    property var nativeView: null
    property var nativeSummary: null
    property int geometryReturnPhase: 1
    SettingsCatalog { id: catalog }
    property Component pageType: StorageConfig { width: parent.width; height: parent.height }
    function find(item, name) {
        if (item.objectName === name) return item;
        for (const child of item.children || []) { const result = find(child, name); if (result) return result; }
        return null;
    }
    function click(name) {
        const item=find(page,name); expect(!!item,"Missing "+name);
        page.contentY=Math.max(0,item.mapToItem(page.contentItem,0,0).y-60);
        pointer.mouseClick(item,Math.max(1,item.width/2),Math.max(1,item.height/2),Qt.LeftButton);
    }
    function expect(condition,message) { if(!condition) throw new Error(message); }
    function checkChart() {
        const usage=find(page,"storage-usage-bar").parent;
        const chart=usage.chart;
        const sum=chart.segments.reduce((sum,p)=>sum+p.bytes,0);
        expect(sum===chart.total,"Chart does not balance: "+sum+"/"+chart.total);
        expect(chart.segments.some(p=>p.kind==="folder"),"No real folders in chart");
        function lum(value) { const c=Qt.darker(value,1); function lin(v){return v<=.04045?v/12.92:Math.pow((v+.055)/1.055,2.4);}return .2126*lin(c.r)+.7152*lin(c.g)+.0722*lin(c.b); }
        for(const part of chart.segments.filter(s=>s.kind==="folder")) {
            const color=usage.segmentColor(part),text=usage.contrastingText(Qt.darker(color,1));
            const a=lum(color),b=lum(text),contrast=(Math.max(a,b)+.05)/(Math.min(a,b)+.05);
            expect(contrast>=4.5,"Segment text contrast too low: "+contrast);
            expect(usage.contrast(color,Appearance.colors.colLayer0)>=3,"Folder segment became background");
        }
        return chart;
    }
    function installGeometry(nextPhase) {
        geometryReturnPhase=nextPhase;
        nativeView=Storage.view;nativeSummary=Storage.summary;Storage.active=false;
        const total=610*1024**3,homeBytes=Math.round(total*.76),varBytes=Math.round(total*.09);
        const homeSource=nativeView.segments.find(s=>s.name==="home");
        const varSource=nativeView.segments.find(s=>s.name==="var") || {name:"var",nodeId:9001,path:fixture+"/var",key:"var"};
        const rows=[Object.assign({},homeSource,{bytes:homeBytes,unstableEntries:783,issueCount:783,readErrors:0,unreadableCount:0,coverageIncomplete:false,coverageUncertain:true,partial:true}),
            Object.assign({},varSource,{bytes:varBytes,unreadableCount:0,unstableEntries:0,partial:false}),
            {name:"subpixel",nodeId:9002,path:fixture+"/subpixel",key:"subpixel",bytes:1,unreadableCount:0,unstableEntries:0,excluded:"",partial:false}];
        const summary=Object.assign({},nativeSummary,{state:"complete",engineState:"finished",errors:0,unreadableCount:0,issueCount:783,unstableEntries:783,
            changesObserved:true,coverageIncomplete:false,coverageUncertain:true,uncertainDirectories:783,issueCodes:{directory_changed:783},excludedCount:8,skipped:8});
        const data=Object.assign({},nativeView,{state:"complete",bytes:total,rows,count:3,offset:0,more:false,coverageIncomplete:false,coverageUncertain:true,
            unreadableCount:0,readErrors:0,unstableEntries:783,segments:[Object.assign({},rows[0],{kind:"folder"}),Object.assign({},rows[1],{kind:"folder"}),
            {kind:"files",name:"Direct entries",path:"",bytes:total-homeBytes-varBytes}]});
        expect(Storage.acceptResult({summary,view:data},true),"Modified-only native result rejected");phase=201;
    }
    function checkGeometry() {
        const usage=find(page,"storage-usage-bar").parent;
        expect(Storage.hasChanges && !Storage.hasWarnings,"Metadata changes reported unreadable");
        expect(find(page,"storage-changes-info").visible && find(page,"storage-changes-info").text.includes("783"),"Changes information missing");
        expect(!find(page,"storage-coverage-warning").visible && find(page,"storage-exclusions-info").visible,"Warnings/exclusions conflated");
        for(let i=0;i<3;i++) {
            const track=find(page,"storage-folder-track-"+i),fill=find(page,"storage-folder-fill-"+i),tiny=find(page,"storage-folder-tiny-"+i);
            if(!track || track.width<=0)return false;
            const expected=track.width*Storage.view.rows[i].bytes/Storage.view.bytes;
            expect(Math.abs(fill.width-expected)<.00001,"Scaled allocation geometry inflated: "+fill.width+" / "+expected);
            expect(fill.width>=0 && fill.width<=track.width && track.clip,"Fill outside its track");
            expect(usage.contrast(fill.color,track.color)>=3,"Fill indistinguishable from track: "+fill.color+" / "+track.color);
            expect(tiny.visible===(i===2),"Subpixel marker changed ratio or missing");
        }
        const track=usage.progressTrackColor();
        expect(usage.contrast(usage.progressFillColor({kind:"free"},track),track)>=3,"Exact track/fill collision not corrected");
        expect(Accounting.boundedRatio(-1,100)===0 && Accounting.boundedRatio(110,100)===1 && Accounting.boundedRatio(1,0)===0 && Accounting.boundedRatio(NaN,1)===0,"Geometry guard invalid");
        checkChart();return true;
    }
    Timer {
        interval:120;running:true;repeat:true
        onTriggered: {
            try {
                if(phase===0) {
                    expect(catalog.pages.some(p=>p.component==="StorageConfig.qml"),"Catalog missing");
                    page=pageType.createObject(view.contentItem);expect(!!page,"Page failed");find(page,"storage-workers").activated(1);phase=100;
                } else if(phase===100) {
                    if(["loading","running"].includes(Storage.analysisState)) {
                        sawLoading=true;
                        expect(!Storage.hasComplete && !find(page,"storage-usage-bar").visible && !find(page,"storage-folders").visible,"Published unfinished native scan");
                        expect(find(page,"storage-analysis-status").visible,"Loading panel missing");
                        return;
                    }
                    if(Quickshell.env("STORAGE_TEST_FATAL")) {
                        if(Storage.analysisState!=="error") return;
                        expect(Storage.scanStatus==="root_open_failed","Native failure lost: "+Storage.scanStatus);
                        expect(!Storage.hasComplete && !Storage.view && !find(page,"storage-usage-bar").visible && !find(page,"storage-folders").visible,"Fatal published prefix");
                        if(failedId<0)failedId=Storage.scanId;
                        expect(Storage.scanId===failedId,"Fatal retried automatically");
                        if(errorWait++<3)return;
                        view.visible=false;page.destroy();console.log("STORAGE_QML_PASS");Qt.quit();return;
                    }
                    expect(!Storage.error,"Native scan error: "+Storage.error);
                    if(!Storage.hasComplete || Storage.scanning)return;
                    expect(sawLoading,"No loading state before native success");
                    expect(Storage.backend.engine==="rust" && Storage.summary.protocol===1,"Rust not active");
                    expect(Storage.summary.engineState===(Quickshell.env("STORAGE_TEST_WARNINGS")?"finished-with-warnings":"finished"),"Wrong native terminal state");
                    expect(Storage.disks.length===3,"Physical disks absent");
                    expect(Storage.volumes.some(v=>v.id==="block:8:1"&&!v.mounted),"Unmounted SATA absent");
                    expect(Storage.volumes.some(v=>v.logical&&v.fs==="fuse.rclone"),"FUSE absent");
                    expect(Storage.selected.mount===fixture,"Wrong default selection");
                    expect(!page.advanced && !find(page,"storage-scan-path").visible,"Custom path prominent");
                    if(Storage.view.chartWidth!==Math.max(240,Math.min(4000,Math.floor(Storage.chartWidth))))return;
                    console.log("DIMS",page.width,view.width,page.baseWidth,find(page,"storage-detail").width,find(page,"storage-usage-bar").parent.width,find(page,"storage-usage-bar").width);
                    const chart=checkChart();
                    expect(Storage.view.rows.length===60 && Storage.view.count===173,"Native pagination lost folders");
                    expect(chart.segments.find(s=>s.kind==="others").count===170,"Others not computed over ALL children at "+Storage.chartWidth+" / "+Storage.view.chartWidth+" / "+find(page,"storage-usage-bar").width+": "+JSON.stringify(chart.segments));
                    const limited=Accounting.chart({state:"complete-with-warnings",path:fixture,bytes:27*1024**3,segments:[{kind:"folder",name:"home",path:home,bytes:27*1024**3}]},Object.assign({},Storage.selected,{used:612*1024**3,total:878*1024**3,reserved:44*1024**3,available:222*1024**3}));
                    expect(limited.total===27*1024**3 && limited.warningDifference===585*1024**3 && limited.unknown===0 && limited.segments.length===1,"585 GiB difference turned into measured files");
                    const rejected=Accounting.chart({state:"running",bytes:27*1024**3,segments:[]},Storage.selected);
                    expect(rejected.total===0 && !rejected.segments.length,"Unfinished scan published chart");
                    if(Quickshell.env("STORAGE_TEST_WARNINGS")) {
                        expect(Storage.hasWarnings && find(page,"storage-coverage-warning").visible,"Warning banner missing");
                        expect(Storage.view.rows.find(r=>r.name==="home").readErrors>0,"Affected branch unmarked");
                        expect(chart.mode==="directory" && chart.unknown===0 && !chart.segments.some(s=>s.kind==="unknown"),"Difference drawn as files");
                        expect(chart.warningDifference===Math.max(0,Storage.selected.used-Storage.view.bytes),"Incorrect warning difference");
                    }
                    expect(Storage.summary.execution.workers_limit===1,"Worker option did not reach Rust");
                    nativeSnapshot=Storage.summary.scanId;scanSequence=Storage.scanId;installGeometry(1);
                } else if(phase===201) {
                    if(!checkGeometry())return;
                    expect(Storage.acceptResult({summary:nativeSummary,view:nativeView},true),"Native result restore failed");
                    Storage.active=true;phase=geometryReturnPhase;
                } else if(phase===1) {
                    const usage=find(page,"storage-usage-bar").parent;
                    const index=usage.chart.segments.findIndex(s=>s.kind==="folder"&&s.name==="home");
                    click("storage-segment-"+index);
                    expect(Storage.highlightedPath===home && Storage.highlightedNodeId>=0,"Native segment selection lost ID");
                    click("storage-enter-highlighted");phase=2;
                } else if(phase===2) {
                    if(Storage.view.path!==home)return;
                    expect(Storage.view.rows.some(r=>r.name==="alice"),"Home child missing");
                    expect(checkChart().segments.some(s=>s.name==="alice"),"Chart did not follow native node");
                    expect(Storage.scanId===scanSequence && Storage.summary.scanId===nativeSnapshot,"Navigation rescanned");
                    click("storage-breadcrumb-0");phase=3;
                } else if(phase===3) {
                    if(Storage.view.path!==fixture)return;
                    expect(Storage.view.nodeId===0 && Storage.summary.scanId===nativeSnapshot,"Back changed snapshot");
                    find(page,"storage-usage-bar").parent.othersSelected();phase=4;
                } else if(phase===4) {
                    if(!Storage.othersOnly || Storage.view.count!==170)return;
                    expect(Storage.view.rows.every(r=>r.name.startsWith("tiny")),"Others contains non-small folders");
                    click("storage-next");phase=5;
                } else if(phase===5) {
                    if(Storage.view.offset!==60)return;
                    expect(Storage.view.rows.length===60 && Storage.summary.scanId===nativeSnapshot,"Paging changed snapshot");
                    Storage.filterFolders("tiny16");phase=6;
                } else if(phase===6) {
                    if(Storage.view.count!==10 || Storage.view.offset!==0)return;
                    expect(Storage.view.segments.find(s=>s.kind==="others").count===170,"Filter distorted chart");
                    click("storage-sort");phase=7;
                } else if(phase===7) {
                    if(Storage.order!=="name")return;
                    Storage.browse(fixture);phase=8;
                } else if(phase===8) {
                    if(Storage.query || Storage.othersOnly || Storage.view.count!==173)return;
                    click("storage-volume-block:8:1");phase=9;
                } else if(phase===9) {
                    expect(!Storage.scanning && !Storage.selected.mounted && Storage.scanId===scanSequence,"Unmounted triggered scan");
                    Storage.select("259:2:ext4");phase=10;
                } else if(phase===10) {
                    if(!Storage.view || Storage.scanning)return;
                    expect(Storage.summary.scanId===nativeSnapshot && Storage.scanId===scanSequence,"Volume return rescanned");
                    checkChart();page.contentY=0;
                    if(Quickshell.env("STORAGE_TEST_SCREENSHOT")) {
                        phase=101;
                        view.contentItem.grabToImage(r=>{r.saveToFile(Quickshell.env("STORAGE_TEST_SCREENSHOT"));test.phase=102;});
                    } else phase=102;
                } else if(phase===101 || phase===111) { return; }
                else if(phase===102) { view.width=460;phase=11; }
                else if(phase===11) {
                    expect(!page.wide,"Narrow mode failed");
                    expect(find(page,"storage-usage-bar").width<view.width && find(page,"storage-folders").width<view.width,"Narrow overflow");
                    if(Storage.view.chartWidth!==Math.max(240,Math.min(4000,Math.floor(Storage.chartWidth))))return;
                    checkChart();page.contentY=0;installGeometry(211);
                } else if(phase===211) {
                    if(Quickshell.env("STORAGE_TEST_SCREENSHOT")) {
                        phase=111;
                        view.contentItem.grabToImage(r=>{r.saveToFile(Quickshell.env("STORAGE_TEST_SCREENSHOT")+"-narrow.png");test.phase=112;});
                    } else phase=112;
                } else if(phase===112) {
                    Storage.analyze(fixture+"/missing");expect(Storage.hasComplete&&Storage.stale,"Refresh discarded old result");phase=12;
                } else if(phase===12) {
                    if(Storage.scanning)return;
                    expect(Storage.analysisState==="error" && Storage.scanStatus==="root_open_failed","Native failure not classified");
                    expect(Storage.hasComplete && Storage.stale && Storage.summary.scanId===nativeSnapshot,"Failed refresh replaced valid snapshot");
                    expect(find(page,"storage-usage-bar").visible && find(page,"storage-folders").visible,"Failed refresh hid previous result");
                    Storage.requestedPath=fixture;click("storage-status-action");phase=13;
                } else if(phase===13) {
                    if(Storage.scanning || !["complete","complete-with-warnings"].includes(Storage.analysisState))return;
                    expect(!Storage.stale && Storage.summary.scanId!==nativeSnapshot,"Success did not replace snapshot");
                    nativeSnapshot=Storage.summary.scanId;
                    Storage.analyze(fixture);Storage.cancel();phase=14;
                } else if(phase===14) {
                    if(Storage.scanning)return;
                    expect(Storage.analysisState==="cancelled" && Storage.hasComplete && Storage.stale,"Cancellation published prefix or lost snapshot");
                    expect(Storage.summary.scanId===nativeSnapshot,"Cancel replaced native snapshot");
                    Storage.analyze(fixture);Storage.select("block:8:1");phase=141;
                } else if(phase===141) {
                    if(Storage.scanning)return;
                    expect(!Storage.selected.mounted && !Storage.view && !Storage.hasComplete,"Late scan result leaked into unmounted selection");
                    Storage.select("259:2:ext4");phase=142;
                } else if(phase===142) {
                    if(!Storage.view || Storage.scanning)return;
                    expect(Storage.summary.scanId===nativeSnapshot,"Switch cancelled or replaced wrong native snapshot");
                    Storage.analyze(fixture);view.visible=false;page.destroy();page=null;phase=15;
                } else if(phase===15) {
                    if(Storage.scanning)return;
                    expect(!Storage.active,"Hidden page remains active");
                    scanSequence=Storage.scanId;view.visible=true;page=pageType.createObject(view.contentItem);
                    expect(Storage.hasComplete && Storage.summary.scanId===nativeSnapshot,"Page recreation lost immediate cached presentation");phase=16;
                } else if(phase===16) {
                    if(!Storage.active || Storage.scanning)return;
                    expect(Storage.summary.scanId===nativeSnapshot && Storage.scanId===scanSequence,"Reopen rescanned cached native snapshot");
                    expect(Storage.fromCache && find(page,"storage-cache-info").visible,"Session reuse not indicated");
                    Storage.select("8:17:ext4");phase=17;
                } else if(phase===17) {
                    if(!Storage.view || Storage.scanning)return;
                    expect(Storage.selected.id==="8:17:ext4","USB selection failed");
                    Storage.refresh();phase=18;
                } else if(phase===18) {
                    if(Storage.loading)return;
                    expect(!Storage.disks.some(d=>d.transport==="usb"),"Removed USB listed");
                    expect(!Storage.selected && Storage.error==="volume-disconnected"&&!Storage.scanning,"Disconnected selection unresolved");
                    view.visible=false;page.destroy();console.log("STORAGE_QML_PASS");Qt.quit();
                }
            } catch(e) {console.error("STORAGE_QML_FAIL",phase,String(e));Qt.quit();}
        }
    }
    Timer { interval:18000;running:true;onTriggered:{console.error("STORAGE_QML_FAIL timeout",test.phase,Storage.error);Qt.quit();} }
}
''')
            (base / "runtime").mkdir(mode=0o700)
            env = dict(os.environ, XDG_RUNTIME_DIR=str(base / "runtime"), QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software",
                       XDG_CONFIG_HOME=str(base / "config"), XDG_STATE_HOME=str(base / "state"),
                       XDG_CACHE_HOME=str(base / "cache"), STORAGE_FIXTURE=str(fixture), STORAGE_SCAN_LOG=str(base / "scans.log"),
                       PATH=str(base / 'bin') + os.pathsep + os.environ['PATH'])
            env['DOTS_STORAGE_EXECUTABLE'] = str(ROOT / 'runtime/storage/target/release/endless-storage')
            try:
                result = subprocess.run([shutil.which("quickshell"), "-p", str(base)], env=env, capture_output=True, text=True, timeout=23)
            finally:
                if denied is not None: denied.chmod(0o700)
            logs = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, logs)
            self.assertIn("STORAGE_QML_PASS", logs)
            for bad in ("STORAGE_QML_FAIL", "ReferenceError:", "TypeError:", "Cannot assign", "Unable to assign", "Binding loop", "recursive rearrange", "is not a type"):
                self.assertNotIn(bad, logs)

    def test_light_palette_offscreen(self):
        extra = {"STORAGE_TEST_LIGHT": "1"}
        if os.environ.get("STORAGE_TEST_SCREENSHOT"):
            extra["STORAGE_TEST_SCREENSHOT"] = os.environ["STORAGE_TEST_SCREENSHOT"] + "-light.png"
        with patch.dict(os.environ, **extra):
            self.test_isolated_page_worker_navigation_and_responsive()

    def test_colliding_theme_tokens_offscreen(self):
        with patch.dict(os.environ, STORAGE_TEST_COLLISION="1"):
            self.test_isolated_page_worker_navigation_and_responsive()

    def test_scaled_layout_offscreen(self):
        with patch.dict(os.environ, STORAGE_TEST_SCALE="1.3"):
            self.test_isolated_page_worker_navigation_and_responsive()

    def test_native_fatal_offscreen(self):
        with patch.dict(os.environ, STORAGE_TEST_FATAL="1"):
            self.test_isolated_page_worker_navigation_and_responsive()

    @unittest.skipIf(os.geteuid() == 0, "unprivileged fixture user required")
    def test_native_warning_offscreen(self):
        with patch.dict(os.environ, STORAGE_TEST_WARNINGS="1"):
            self.test_isolated_page_worker_navigation_and_responsive()

    def test_qt6_syntax(self):
        formatter = Path("/usr/lib/qt6/bin/qmlformat")
        if not formatter.exists(): self.skipTest("Qt6 qmlformat unavailable")
        for name in ("services/Storage.qml", "modules/settings/StorageConfig.qml", *["modules/settings/storage/"+p.name for p in (SOURCE / "modules/settings/storage").glob("*.qml")]):
            result = subprocess.run([str(formatter), str(SOURCE / name)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__": unittest.main()
