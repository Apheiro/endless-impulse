"""Real QML with an isolated AuthFlow fixture; no native listener is constructed."""
import os
import re
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/quickshell'


class PolkitQmlTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('quickshell'), 'Quickshell required')
    def test_flow_panel_and_grab_lifecycle(self):
        with tempfile.TemporaryDirectory(prefix='polkit-qml-') as tmp:
            base = Path(tmp)
            for name in ('assets', 'scripts', 'defaults', 'translations', 'GlobalStates.qml'):
                (base / name).symlink_to(SOURCE / name)
            def write(name, text):
                path = base / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            def copy(name): write(name, (SOURCE / name).read_text())
            for name in ('PolkitPanel', 'PolkitPrompt'):
                copy('modules/shared/widgets/' + name + '.qml')
            for name in ('StyledText', 'MaterialSymbol', 'RippleButton', 'MaterialTextField',
                         'StyledComboBox', 'StateLayer', 'PointingHandInteraction', 'StyledRectangularShadow',
                         'PanelSurface', 'AuthenticationFocusGrab', 'StyledScrollBar', 'StyledFlickable', 'StyledListView'):
                copy('modules/shared/primitives/common/' + name + '.qml')
            write('modules/shared/primitives/common/StyledToolTip.qml', 'import QtQuick\nItem {property string text;property bool extraVisibleCondition:true}')
            for name in ('WindowDialogTitle', 'WindowDialogParagraph', 'DialogButton'):
                copy('modules/shared/primitives/dialogs/' + name + '.qml')
            copy('modules/shared/functions/ColorUtils.qml')
            write('services/Translation.qml', 'pragma Singleton\nimport QtQuick\nQtObject {function tr(text){return text}}')
            write('modules/shared/Config.qml', 'pragma Singleton\nimport QtQuick\nQtObject {property var options:({appearance:{reducedMotion:false},interactions:{scrolling:{fasterTouchpadScroll:false}}})}')
            appearance = (SOURCE / 'modules/shared/Appearance.qml').read_text()
            colors = {key: '#24232a' for key in re.findall(r'property color (col\w+):', appearance)}
            for key in colors:
                if key.startswith('colOn'): colors[key] = '#eeeeee'
            m3 = dict(re.findall(r'property color (m3\w+): "(#[^"]+)"', appearance))
            props = dict(colors=colors, m3colors=dict(m3, darkmode=True),
                font=dict(family=dict(main='Sans', numbers='Sans', title='Sans', iconMaterial='Sans'),
                          pixelSize=dict(small=14, smaller=12, normal=15, larger=18, title=24),
                          variableAxes=dict(main={}, numbers={}, title={})),
                rounding=dict(small=8, normal=16, medium=12, large=20, full=999, unsharpenmore=8),
                sizes=dict(elevationMargin=12, contextMenuWidth=240, textInputHorizontalPadding=12,textInputVerticalPadding=8,textInputMinimumHeight=40))
            write('modules/shared/Appearance.qml', 'pragma Singleton\nimport QtQuick\nQtObject {' +
                  ''.join('property var '+key+':'+json.dumps(value)+'\n' for key,value in props.items()) + """
 function animationDuration(ms){return 0;}
 property var animationCurves:({standardDecel:[0,0,1,1,1,1]})
 property QtObject animation:QtObject {
 property QtObject scroll:fastAnimation
 property QtObject elementMove:fastAnimation
 property QtObject elementMoveEnter:fastAnimation
 property QtObject elementMoveFast:QtObject {id:fastAnimation;property int duration:90;property int type:Easing.Linear;property var bezierCurve:[0,0,1,1,1,1];property Component numberAnimation:NumberAnimation{duration:0};property Component colorAnimation:ColorAnimation{duration:0}}
 }
}""")
            (base / 'mock').mkdir()
            service = (SOURCE / 'services/PolkitService.qml').read_text().replace('import Quickshell.Services.Polkit', 'import "../mock"')
            (base / 'services/PolkitService.qml').write_text(service)
            (base / 'services/AuthenticationFocusState.qml').write_text('''pragma Singleton
import QtQuick
QtObject {
 readonly property bool grabReady:true
 property bool host:false
 property bool owner:true
 property bool localActive:false
 property bool remoteActive:false
 readonly property bool active:localActive||remoteActive
 readonly property bool presentationReady:localActive
}
''')
            panel = (SOURCE / 'modules/shared/widgets/PolkitPanel.qml').read_text()
            panel = panel.replace('import Quickshell.Wayland', 'import "../../../mock"')
            panel = panel.replace('PanelWindow {', 'MockPanelWindow {').replace('anchors.bottom: true', 'property bool bottomAnchor: true')
            panel = '\n'.join(line for line in panel.splitlines() if 'WlrLayershell.' not in line)
            panel = panel.replace('ExclusionMode.Ignore', '0').replace('visible: host.mapped', 'property bool mappedVisible: host.mapped')
            write('modules/shared/widgets/PolkitPanel.qml', panel)
            write('mock/MockPanelWindow.qml', 'import QtQuick\nItem {property var screen;property int exclusionMode;property real exclusiveZone;property color color;property var mask}')
            (base / 'mock/PolkitAgent.qml').write_text('''import QtQuick
QtObject {
 property bool isActive:false
 property bool isRegistered:true
 property QtObject flow:null
}
''')
            grab = (SOURCE / 'modules/shared/primitives/common/AuthenticationFocusGrab.qml').read_text().replace('import Quickshell.Hyprland', 'import "../../../../mock"').replace('id: root', 'id: root\n    property alias nativeGrab: grab')
            (base / 'modules/shared/primitives/common/AuthenticationFocusGrab.qml').write_text(grab)
            (base / 'mock/HyprlandFocusGrab.qml').write_text('''import QtQuick
QtObject {
 objectName:"native-grab"
 property bool active:false
 property var windows:[]
 signal cleared()
 onActiveChanged:if(!active)cleared()
}
''')
            (base / 'shell.qml').write_text('''//@ pragma UseQApplication
//@ pragma Env QT_QUICK_CONTROLS_STYLE=Basic
import QtQuick
import Quickshell
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets
import qs.modules.shared.primitives.common
ShellRoot {
 id:root
 property int step:0
 property int dismissals:0
 property var smallOutput:({name:"fixture-small",width:320,height:240})
 property var wideOutput:({name:"fixture-wide",width:1280,height:720})
 property real bottomY:0
 property real exitProgress:0
 property QtObject flow:QtObject {
  property bool isSuccessful:false
  property bool isCompleted:false
  property bool isResponseRequired:true
  property bool responseVisible:false
  property string message:"Fixture authorization"
  property string inputPrompt:"Response"
  property string supplementaryMessage:""
  property bool supplementaryIsError:false
  property bool failed:false
  property var identities:[{displayName:"Fixture A"},{displayName:"Fixture B"}]
  property var selectedIdentity:null
  signal authenticationFailed()
  property int submissions:0
  function submit(value){if(value!=="mock-response-never-log-4591")throw Error("response not delivered");submissions++;isResponseRequired=false;}
  function cancelAuthenticationRequest(){isCompleted=true;}
 }
 AuthenticationFocusGrab {id:grab;active:true;onCleared:root.dismissals++}
 PolkitPrompt {id:prompt;width:440;height:implicitHeight}
 // Compile the production panel (do not map a Wayland window in offscreen QA).
 PolkitPanel{id:panelHost}
 function expect(value,message){if(!value)throw Error(message);}
 function find(item,name){if(item.objectName===name)return item;for(const child of [...(item.children||[]),...(item.resources||[]),...(item.item?[item.item]:[])]){const result=find(child,name);if(result)return result;}return null;}
 Timer {
  interval:60;running:true;repeat:true
  onTriggered:{try{
   const input=root.find(prompt,"polkit-response");
   root.expect(input,"response field");
   if(root.step===0){
    root.expect(grab.grabbing,"normal focus");
    panelHost.presentation.selectScreen([root.smallOutput,root.wideOutput],"fixture-wide");
    root.expect(panelHost.presentation.selectedScreen===root.wideOutput,"focused monitor selection");
    panelHost.presentation.selectScreen([root.smallOutput,root.wideOutput],"missing");
    root.expect(panelHost.presentation.selectedScreen===root.smallOutput,"monitor fallback");
    PolkitService.agent.flow=root.flow;PolkitService.agent.isActive=true;
   }else if(root.step===1){
    root.expect(AuthenticationFocusState.active&&!grab.grabbing,"guard before presentation");
    const panel=panelHost.presentation.panelWindow;
    const surface=panelHost.presentation.card;
    root.expect(panel&&panel.mappedVisible&&surface,"single mapped card");
    root.expect(surface.y>=panel.shadowMargin,"entry from below");
    root.bottomY=panel.shadowMargin;
    panelHost.presentation.selectScreen([root.smallOutput],"fixture-small");
    root.expect(panel.implicitWidth<=320&&panel.implicitHeight<=240,"small screen bounds");
    input.text="mock-response-never-log-4591";prompt.submit();prompt.submit();root.expect(root.flow.submissions===1,"duplicate submit while pending");root.expect(input.text===""&&!PolkitService.interactionAvailable,"clear on submit");
    root.expect(PolkitService.conversationActive&&panelHost.presentation.mapped&&AuthenticationFocusState.active,"pending response must not close or release guard");
    root.flow.supplementaryMessage="Informational message";
    root.flow.failed=true;root.flow.authenticationFailed();root.flow.isResponseRequired=true;
   }else if(root.step===2){
    root.expect(PolkitService.interactionAvailable&&input.text==="","retry input");
    root.expect(root.find(prompt,"polkit-feedback").text==="Authentication failed. Please try again.","denial must remain visible even after supplementary info");
    const surface=panelHost.presentation.card;
    root.expect(Math.abs(surface.y-root.bottomY)<0.01,"retry moved bottom anchor");
    root.expect(panelHost.presentation.selectedScreen===root.smallOutput,"retry changed selected monitor");
    input.text="fixture";root.flow.responseVisible=true;root.flow.inputPrompt="Second factor";
    root.expect(input.text==="","multifactor clearing");
    PolkitService.cancel();root.expect(!PolkitService.conversationActive&&input.text==="","cancel");
    root.expect(AuthenticationFocusState.active&&!grab.grabbing,"guard retained during exit");
   }else if(root.step===3){
    root.expect(panelHost.presentation.progress>0&&panelHost.presentation.progress<1,"animated exit");
    root.expect(AuthenticationFocusState.active&&!grab.grabbing,"guard during animated exit");
    root.exitProgress=panelHost.presentation.progress;
    root.flow.isCompleted=false; // A request arriving during exit reverses it.
   }else if(root.step===4){
    root.expect(panelHost.presentation.progress>root.exitProgress&&AuthenticationFocusState.active,"chained request reverses exit");
    input.text="fixture";PolkitService.selectIdentity(root.flow.identities[1]);
    root.expect(input.text===""&&root.flow.selectedIdentity===root.flow.identities[1],"identity change clears input");
    root.flow.isSuccessful=true;root.flow.isCompleted=true;
   }else if(root.step===5){
    root.expect(AuthenticationFocusState.active&&!grab.grabbing,"completion retains guard during exit");
   }else if(root.step===6){
    root.expect(grab.grabbing&&root.dismissals===0,"restore without delayed clear");
    root.expect(!panelHost.presentation.panelWindow.mappedVisible,"success must unmap without reopening");
    PolkitService.agent.isActive=false;PolkitService.agent.flow=null;
    root.flow.isCompleted=false;root.flow.isSuccessful=false;
    Config.options=Object.assign({},Config.options,{appearance:{reducedMotion:true}});
    PolkitService.agent.flow=root.flow;PolkitService.agent.isActive=true;
   }else if(root.step===7){
    root.expect(panelHost.presentation.progress===1&&AuthenticationFocusState.active,"reduced motion entry");
    PolkitService.cancel();
   }else if(root.step===8){
    root.expect(!panelHost.presentation.mapped&&!AuthenticationFocusState.active&&grab.grabbing,"reduced motion exit");
    grab.nativeGrab.cleared();root.expect(root.dismissals===1,"normal outside dismissal");
    grab.requestFocus();
   }else if(root.step===9){
    grab.nativeGrab.cleared();root.expect(root.dismissals===2,"repeat manual grab");
    PolkitService.agent.isActive=false;PolkitService.agent.flow=null;
    console.log("POLKIT_QML_OK");Qt.quit();
   }
   root.step++;
  }catch(error){console.error("POLKIT_QML_FAILED "+error);Qt.quit();}}
 }
 Timer {interval:4000;running:true;onTriggered:{console.error("POLKIT_QML_FAILED timeout");Qt.quit();}}
}
''')
            env = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software',
                       XDG_RUNTIME_DIR=tmp, XDG_CONFIG_HOME=tmp, XDG_CACHE_HOME=tmp,
                       XDG_STATE_HOME=tmp, QT_QPA_PLATFORMTHEME='', DOTS_SHELL_SOURCE=tmp)
            result = subprocess.run([shutil.which('quickshell'), '-p', tmp], env=env,
                                    capture_output=True, text=True, timeout=10)
            logs = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, logs)
            self.assertIn('POLKIT_QML_OK', logs)
            self.assertNotIn('mock-response-never-log-4591', logs)
            for error in ('POLKIT_QML_FAILED', 'ReferenceError', 'TypeError', 'Cannot assign', 'Unable to assign', 'Binding loop'):
                self.assertNotIn(error, logs)


if __name__ == '__main__': unittest.main()
