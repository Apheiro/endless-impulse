"""Exercise the actual Quickshell service against a disposable bridge, never Firewalld."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'src/quickshell'


class FirewalldServiceTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('quickshell'), 'Quickshell required')
    def test_worker_exit_protocol_failure_timeout_and_manual_recovery(self):
        with tempfile.TemporaryDirectory(prefix='firewall-lifecycle-') as tmp:
            base = Path(tmp)
            (base / 'services').mkdir()
            service = (SOURCE / 'services/FirewalldControl.qml').read_text().replace('interval: 300000', 'interval: 250')
            (base / 'services/FirewalldControl.qml').write_text(service)
            (base / 'scripts/firewalld').mkdir(parents=True)
            (base / 'scripts/firewalld/control.py').write_text('''import json,sys,os,time
from pathlib import Path
marker=Path(__file__).with_name('started')
if not marker.exists():
 marker.touch()
 print(json.dumps({'ok':False,'error':'Bootstrap failed','operationState':'communication-error'}),flush=True)
 sys.exit(1)
print(json.dumps({'event':'ready'}),flush=True)
for line in sys.stdin:
 request=json.loads(line)
 action=request['action']
 if action=='crash':sys.exit(7)
 if action=='malformed':print('{broken',flush=True);continue
 if action=='missing-id':print(json.dumps({'ok':True}),flush=True);continue
 if action=='bad-schema':print(json.dumps({'ok':'yes','requestId':request['requestId']}),flush=True);continue
 if action=='silent-auth':print(json.dumps({'event':'authorization-required','requestId':request['requestId']}),flush=True);continue
 if action=='stall':time.sleep(5);continue
 if action=='inspect':print(json.dumps({'ok':False,'error':'Permission expired','operationState':'access-denied','requestId':request['requestId']}),flush=True);continue
 if action=='stale':
  print(json.dumps({'requestId':request['requestId']-1,'ok':True,'snapshot':{'connected':False,'complete':False,'scopes':{}}}),flush=True)
 print(json.dumps({'requestId':request['requestId'],'ok':True,'operationState':'applied','snapshot':{'connected':True,'complete':True,'state':'connected','lastUpdated':'historical','scopes':{},'services':[],'activeZones':[],'differences':[],'workerPid':os.getpid()}}),flush=True)
 if action=='idle-exit':time.sleep(.06);sys.exit(9)
''')
            (base / 'shell.qml').write_text('''import QtQuick
import Quickshell
import qs.services
ShellRoot {
 id:root
 property int phase:-1
 property int failureIndex:0
 property int ticks:0
 property int pid:0
 property var failures:["crash","idle-exit","malformed","missing-id","bad-schema","silent-auth","stall","inspect"]
 function fail(message){console.error("FIREWALL_LIFECYCLE_FAILED "+message);Qt.quit();}
 Component.onCompleted:FirewalldControl.active=true
 Timer {
  interval:20;running:true;repeat:true
  onTriggered:{
   if(FirewalldControl.busy)return;
   if(root.phase===-1){
    if(FirewalldControl.editable || !FirewalldControl.retryRequired || FirewalldControl.error!=="Bootstrap failed"){root.fail("bootstrap failure");return;}
    if(++root.ticks<6)return;
    FirewalldControl.refresh();root.phase=0;
   }else if(root.phase===0){
    if(!FirewalldControl.editable){root.fail("initial snapshot");return;}
    root.pid=FirewalldControl.snapshot.workerPid;
    FirewalldControl.start({action:"stale",allowInteraction:false});root.phase=1;
   }else if(root.phase===1){
    if(!FirewalldControl.editable || FirewalldControl.snapshot.workerPid!==root.pid){root.fail("stale response or PID changed");return;}
    FirewalldControl.start({action:root.failures[root.failureIndex],allowInteraction:false});root.phase=2;root.ticks=0;
    if(root.failures[root.failureIndex]==="idle-exit")FirewalldControl.active=false;
   }else if(root.phase===2){
    if(root.failures[root.failureIndex]==="idle-exit" && FirewalldControl.editable && ++root.ticks<6)return;
    if(FirewalldControl.editable || !FirewalldControl.retryRequired || FirewalldControl.authorizing || Object.keys(FirewalldControl.snapshot.scopes).length || FirewalldControl.lastValidRead!=="historical" || !FirewalldControl.error){root.fail("failure retained editable state");return;}
    if(++root.ticks<6)return;
    // Navigation and passive refresh cannot restart a failed request.
    const serial=FirewalldControl.requestSerial;
    FirewalldControl.active=false;FirewalldControl.active=true;FirewalldControl.refresh(false);
    if(FirewalldControl.busy || FirewalldControl.requestSerial!==serial){root.fail("automatic retry");return;}
    FirewalldControl.refresh();root.phase=3;
   }else{
    if(!FirewalldControl.editable || FirewalldControl.retryRequired){root.fail("manual recovery");return;}
    if(root.failures[root.failureIndex]!=="inspect" && FirewalldControl.snapshot.workerPid===root.pid){root.fail("dead worker reused");return;}
    root.pid=FirewalldControl.snapshot.workerPid;
    if(++root.failureIndex<root.failures.length){root.phase=1;return;}
    console.log("FIREWALL_LIFECYCLE_OK");FirewalldControl.active=false;Qt.quit();
   }
  }
 }
 Timer{interval:7000;running:true;onTriggered:root.fail("test watchdog");}
}
''')
            env = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software',
                       XDG_RUNTIME_DIR=tmp, XDG_CONFIG_HOME=tmp, XDG_CACHE_HOME=tmp,
                       XDG_STATE_HOME=tmp, QT_QPA_PLATFORMTHEME='', DOTS_SHELL_SOURCE=tmp)
            result = subprocess.run([shutil.which('quickshell'), '-p', tmp], env=env,
                                    capture_output=True, text=True, timeout=10)
            logs = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, logs)
            self.assertIn('FIREWALL_LIFECYCLE_OK', logs)
            for error in ('FIREWALL_LIFECYCLE_FAILED', 'ReferenceError', 'TypeError', 'Cannot assign', 'Unable to assign'):
                self.assertNotIn(error, logs)

    @unittest.skipUnless(shutil.which('quickshell'), 'Quickshell required')
    def test_bounded_process_and_serialized_refresh(self):
        with tempfile.TemporaryDirectory(prefix='firewall-service-') as tmp:
            base = Path(tmp)
            (base / 'services').mkdir()
            shutil.copy(SOURCE / 'services/FirewalldControl.qml', base / 'services')
            (base / 'modules/settings').mkdir(parents=True)
            shutil.copy(SOURCE / 'modules/settings/SettingsCatalog.qml', base / 'modules/settings')
            (base / 'services/Translation.qml').write_text('pragma Singleton\nimport QtQuick\nQtObject {function tr(text){return text;}}')
            (base / 'scripts/firewalld').mkdir(parents=True)
            (base / 'scripts/firewalld/control.py').write_text('''import json,sys,time
print(json.dumps({"event":"ready"}),flush=True)
for payload in sys.stdin:
 request=json.loads(payload)
 time.sleep(.03)
 if request.get('action')=='bootstrap-failure':
  print(json.dumps({"requestId":request["requestId"],"ok":False,"error":"Host CLI unavailable","operationState":"communication-error"}),flush=True)
  continue
 print(json.dumps({"requestId":request["requestId"],"ok":True,"operationState":"applied","snapshot":{"connected":True,"complete":True,"state":"connected","lastUpdated":"2026-11-03T12:00:00Z","revision":"fixture","scopes":{},"services":[],"activeZones":[],"differences":[]}}),flush=True)
''')
            (base / 'shell.qml').write_text('''import QtQuick
import Quickshell
import qs.services
import qs.modules.settings
ShellRoot {
 SettingsCatalog {id:catalog}
 Component.onCompleted: {FirewalldControl.active=true;FirewalldControl.refresh();}
 Timer {
  interval:40;running:true;repeat:true
  property int phase:0
  onTriggered: {
   if(FirewalldControl.busy)return;
   if(phase===0) {
    const index=catalog.pages.findIndex(page=>page.component==="FirewallConfig.qml");
    if(catalog.pages.length!==22 || index<0 || !catalog.matches(index,"firewalld") || !catalog.matches(index,"seguridad puertos")) {console.error("FIREWALL_SERVICE_FAILED catalog");Qt.quit();return;}
    if(!FirewalldControl.editable || !FirewalldControl.lastValidRead) {console.error("FIREWALL_SERVICE_FAILED snapshot");Qt.quit();return;}
    FirewalldControl.apply({action:"add-service",scope:"runtime",zone:"fixture",value:"http",revision:"fixture"});
    FirewalldControl.refresh();
    if(FirewalldControl.request.action!=="add-service") {console.error("FIREWALL_SERVICE_FAILED serialization");Qt.quit();return;}
    phase++;
   } else if(phase===1) {
    if(FirewalldControl.result!=="applied" || FirewalldControl.error){console.error("FIREWALL_SERVICE_FAILED result");Qt.quit();return;}
    FirewalldControl.start({action:"bootstrap-failure"});phase++;
   } else {
    if(FirewalldControl.editable || !FirewalldControl.retryRequired || FirewalldControl.error!=="Host CLI unavailable")console.error("FIREWALL_SERVICE_FAILED stale editable snapshot");
    else console.log("FIREWALL_SERVICE_OK");
    FirewalldControl.active=false;
    Qt.quit();
   }
  }
 }
 Timer {interval:4000;running:true;onTriggered:{console.error("FIREWALL_SERVICE_FAILED timeout");Qt.quit();}}
}
''')
            env = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software',
                       XDG_RUNTIME_DIR=tmp, XDG_CONFIG_HOME=tmp, XDG_CACHE_HOME=tmp, XDG_STATE_HOME=tmp,
                       QT_QPA_PLATFORMTHEME='', DOTS_SHELL_SOURCE=tmp)
            result = subprocess.run([shutil.which('quickshell'), '-p', tmp], env=env, capture_output=True, text=True, timeout=8)
            logs = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, logs)
            self.assertIn('FIREWALL_SERVICE_OK', logs)
            for error in ('FIREWALL_SERVICE_FAILED', 'ReferenceError', 'TypeError', 'Cannot assign', 'Unable to assign'):
                self.assertNotIn(error, logs)


if __name__ == '__main__':
    unittest.main()
