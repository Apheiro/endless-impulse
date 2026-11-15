"""Real service + focus component, with a fake compositor and bridge, offscreen.

The mock grab exposes the protocol's cleared signal. This checks QML bindings
and the pre-prompt handshake, not compositor focus or the host Polkit agent.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'src/quickshell'


class FirewallFocusTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('quickshell'), 'Quickshell required')
    def test_auth_handshake_denial_timeout_reentry_and_grab_restoration(self):
        with tempfile.TemporaryDirectory(prefix='firewall-focus-') as tmp:
            base = Path(tmp)
            for directory in ('services', 'modules/settings', 'scripts/firewalld', 'mock', 'modules/shared/primitives/common'):
                (base / directory).mkdir(parents=True)
            service = (SOURCE / 'services/FirewalldControl.qml').read_text().replace('interval: 30000\n', 'interval: 80\n')
            (base / 'services/FirewalldControl.qml').write_text(service)
            focus = (SOURCE / 'modules/settings/SettingsFocusGrab.qml').read_text()
            common = (SOURCE / 'modules/shared/primitives/common/AuthenticationFocusGrab.qml').read_text().replace('import Quickshell.Hyprland', 'import "../../../../mock"')
            (base / 'modules/shared/primitives/common/AuthenticationFocusGrab.qml').write_text(common)
            (base / 'services/AuthenticationFocusState.qml').write_text('pragma Singleton\nimport QtQuick\nQtObject {property bool active:false; readonly property bool grabReady:true}')
            (base / 'modules/settings/SettingsFocusGrab.qml').write_text(focus)
            (base / 'mock/HyprlandFocusGrab.qml').write_text('''import QtQuick
QtObject {property bool active:false; property var windows:[]; signal cleared();}
''')
            (base / 'scripts/firewalld/control.py').write_text('''import json,sys,time
print(json.dumps({"event":"ready"}),flush=True)
for payload in sys.stdin:
 from pathlib import Path
 request=json.loads(payload)
 path=Path(__file__).with_name('calls')
 n=int(path.read_text())+1 if path.exists() else 1
 path.write_text(str(n))
 if n != 6:
     assert request.get('allowInteraction') is True, request
     print(json.dumps({'event':'authorization-required','requestId':request['requestId']}),flush=True)
     assert json.loads(sys.stdin.readline())=={'event':'authorize','requestId':request['requestId']}
     time.sleep(.06)
 state='access-denied' if n in (1,3) else 'timeout' if n==4 else 'connected'
 complete=state=='connected'
 print(json.dumps({'requestId':request['requestId'],'ok':complete,'operationState':state,'error':'' if complete else state,
  'snapshot':{'connected':True,'complete':complete,'state':state,'scopes':{},'services':[],
  'activeZones':[],'differences':[],'lastUpdated':'fixture' if complete else None}}),flush=True)
''')
            (base / 'shell.qml').write_text('''import QtQuick
import Quickshell
import qs.services
import qs.modules.settings
ShellRoot {
 id:root
 property int phase:0
 property int ticks:0
 property int challenges:0
 property int dismissed:0
 property bool preview:false
 property QtObject mainWindow:QtObject{}
 property QtObject previewWindow:QtObject{}
 SettingsFocusGrab {
  id:grab;shown:true;authorizing:FirewalldControl.authorizing
  windows:root.preview ? [root.mainWindow,root.previewWindow] : [root.mainWindow]
  onDismissed:root.dismissed++
 }
 function fail(message) {console.error("FIREWALL_FOCUS_FAILED "+message);Qt.quit();}
 Connections {
  target:FirewalldControl
  function onAuthorizingChanged() {
   if(FirewalldControl.authorizing) {
    root.challenges++;
    Qt.callLater(()=>{
     if(grab.active)root.fail("grab still active before prompt");
     grab.cleared();
     if(root.dismissed)root.fail("authorization dismissed Settings");
    });
   }
  }
 }
 Component.onCompleted: {
  if(!grab.active) {fail("initial grab");return;}
  grab.cleared();
  if(dismissed!==1) {fail("ordinary outside focus did not dismiss");return;}
  dismissed=0;
  FirewalldControl.active=true;
 }
 Timer {
  interval:20;running:true;repeat:true
  onTriggered: {
   if(FirewalldControl.busy)return;
   if(root.phase===0) {
    if(!FirewalldControl.retryRequired || FirewalldControl.authorizing || root.challenges!==1) {root.fail("initial native authorization was not requested");return;}
    FirewalldControl.active=false;FirewalldControl.active=true;
    if(++root.ticks<12)return;
    FirewalldControl.refresh();root.phase=1;
   } else if(root.phase===1) {
    if(!grab.active || !FirewalldControl.editable || root.challenges!==2) {root.fail("success did not restore grab");return;}
    root.preview=true;
    if(grab.windows.length!==2) {root.fail("preview windows");return;}
    FirewalldControl.apply({action:"remove-service",value:"ssh"});root.phase=2;root.ticks=0;
   } else if(root.phase===2) {
    if(!grab.active || !FirewalldControl.retryRequired || FirewalldControl.authorizing || root.challenges!==3) {root.fail("cancel/denial");return;}
    FirewalldControl.active=false;FirewalldControl.active=true;
    if(++root.ticks<12)return;
    FirewalldControl.refresh();root.phase=3;
   } else if(root.phase===3) {
    if(!grab.active || FirewalldControl.snapshot.state!=="timeout" || !FirewalldControl.retryRequired || root.challenges!==4) {root.fail("timeout restoration");return;}
    FirewalldControl.refresh();root.phase=4;root.ticks=0;
   } else {
    if(!grab.active || !FirewalldControl.editable || root.challenges!==5) {root.fail("manual recovery");return;}
    if(FirewalldControl.request.allowInteraction) {
     if(++root.ticks<12)return;
     root.fail("timer did not refresh silently");return;
    }
    root.preview=false;
    if(grab.windows.length!==1) {root.fail("preview removal");return;}
    grab.cleared();
    if(root.dismissed!==1) {root.fail("outside focus after auth");return;}
    FirewalldControl.active=false;
    console.log("FIREWALL_FOCUS_OK");Qt.quit();
   }
  }
 }
 Timer {interval:4000;running:true;onTriggered:root.fail("watchdog");}
}
''')
            env = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software',
                       XDG_RUNTIME_DIR=tmp, XDG_CONFIG_HOME=tmp, XDG_CACHE_HOME=tmp,
                       XDG_STATE_HOME=tmp, QT_QPA_PLATFORMTHEME='', DOTS_SHELL_SOURCE=tmp)
            result = subprocess.run([shutil.which('quickshell'), '-p', tmp], env=env,
                                    capture_output=True, text=True, timeout=8)
            logs = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, logs)
            self.assertIn('FIREWALL_FOCUS_OK', logs)
            for error in ('FIREWALL_FOCUS_FAILED', 'ReferenceError', 'TypeError', 'Cannot assign', 'Unable to assign'):
                self.assertNotIn(error, logs)
            self.assertEqual((base / 'scripts/firewalld/calls').read_text(), '6', logs)


if __name__ == '__main__':
    unittest.main()
