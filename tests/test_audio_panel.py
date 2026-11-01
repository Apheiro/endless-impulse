"""Audio panel: read-only startup, stable refresh and all desktop audio pages."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'src/quickshell'
spec=importlib.util.spec_from_file_location('audio_control',SOURCE/'scripts/audio/control.py')
audio=importlib.util.module_from_spec(spec);spec.loader.exec_module(audio)

class AudioActionTests(unittest.TestCase):
    def setUp(self):
        self.device=dict(index=3,name='test output',properties={'object.serial':'44'},volume={'left':{},'right':{}})
        self.data={'sinks':[self.device],'sources':[],'sink_inputs':[dict(index=5,properties={'object.serial':'66'},volume={'mono':{}})]}
        self.raw=patch.object(audio,'raw',return_value=self.data);self.raw.start();self.addCleanup(self.raw.stop)
        self.runner=patch.object(audio,'run');self.run=self.runner.start();self.addCleanup(self.runner.stop)
    def test_volume_and_channels_use_arguments(self):
        audio.action(dict(action='volume',kind='sink',id='3',serial='44',values=[30,40]))
        self.run.assert_called_once_with(['pactl','set-sink-volume','3','30.00%','40.00%'])
    def test_reused_ids_and_invalid_volumes_never_mutate(self):
        for payload in [dict(action='mute',value=True,serial='old'),dict(action='volume',value=float('nan')),dict(action='volume',values=[10]),dict(action='volume',value=201)]:
            request=dict(kind='sink',id='3',serial='44');request.update(payload)
            with self.assertRaises(ValueError):audio.action(request)
        self.run.assert_not_called()
    def test_stream_routing_validates_destination_identity(self):
        audio.action(dict(action='move',kind='sink-input',id='5',serial='66',target='3',targetSerial='44'))
        self.run.assert_called_once_with(['pactl','move-sink-input','5','3'])
        self.run.reset_mock()
        with self.assertRaises(ValueError):audio.action(dict(action='move',kind='sink-input',id='5',serial='66',target='3',targetSerial='old'))
        self.run.assert_not_called()
    def test_clock_requires_known_integer_with_sensible_range(self):
        for key,value in [('clock.force-rate',20),('clock.force-quantum',5),('clock.force-rate',48000.5),('unknown',10)]:
            with self.assertRaises(ValueError):audio.action(dict(action='clock',key=key,value=value))
        self.run.assert_not_called()
        audio.action(dict(action='clock',key='clock.force-rate',value=0))
        self.run.assert_called_once_with(['pw-metadata','-n','settings','0','clock.force-rate','0'])
    def test_scroll_resolves_real_default_and_uses_slider_mutation_path(self):
        self.device['volume']={'left':{'value':32768},'right':{'value':32768}}
        self.run.return_value={'default_sink_name':'test output'}
        audio.action(dict(action='adjust-default',steps=3,limit=100))
        self.assertEqual(self.run.call_args.args[0],['pactl','set-sink-volume','3','56.00%'])
        self.run.reset_mock()
        audio.action(dict(action='adjust-default',steps=-100,limit=100))
        self.assertEqual(self.run.call_args.args[0],['pactl','set-sink-volume','3','0.00%'])

    def test_port_connections_check_direction_and_recycled_ids(self):
        def port(identity,token,direction):return dict(id=identity,type='PipeWire:Interface:Port',info={'props':{'object.serial':token},'direction':direction})
        self.run.return_value=[port(1,11,'out'),port(2,22,'in')]
        audio.action(dict(action='connect',output='1',outputSerial='11',input='2',inputSerial='22',passive=True))
        self.assertEqual(self.run.call_args.args[0],['pw-link','-P','1','2'])
        self.run.reset_mock();self.run.return_value=[port(1,11,'in'),port(2,22,'in')]
        with self.assertRaises(ValueError):audio.action(dict(action='connect',output='1',outputSerial='11',input='2',inputSerial='22'))
        self.assertEqual(self.run.call_count,1)

class EasyEffectsRoutingTests(unittest.TestCase):
    def device(self, identity, name, processor=False, enabled=False, monitor=False):
        properties={'object.id':identity, 'node.name':name}
        if processor:
            properties.update({'application.id':'com.github.wwmm.easyeffects', 'monitor.channel-volumes':str(enabled).lower()})
        if monitor:name+='.monitor'
        return audio.normalize(dict(index=identity,name=name,properties=properties), 'source' if monitor else 'sink')

    def test_actual_linked_destination_is_independent_of_default_and_handles_cycles(self):
        processor=self.device(1,'easyeffects_sink',True)
        current=self.device(3,'Headphones'); current['default']=True
        other=self.device(4,'Speakers')
        result={'sink':[processor,current,other], 'source':[]}
        def node(identity,name,client):
            return dict(id=identity,type='PipeWire:Interface:Node',info={'props':{'node.name':name,'client.id':client}})
        def link(source,target,state='active'):
            return dict(type='PipeWire:Interface:Link',info={'output-node-id':source,'input-node-id':target,'state':state})
        graph=[node(1,'easyeffects_sink',10),node(2,'output_filter',10),node(3,'Headphones',20),node(4,'Speakers',20),link(1,2),link(2,1),link(2,4),link(2,3,'error')]
        audio.describe_processing(result,graph)
        self.assertEqual([device['name'] for device in processor['routeDevices']],['Speakers'])
        self.assertFalse(processor['volumeEffective'])
        self.assertTrue(current['volumeEffective'])
        graph.pop(5); graph.pop(4) # The processor loses its links; don't invent a default route.
        audio.describe_processing(result,graph)
        self.assertEqual(processor['routeDevices'],[])

    def test_explicit_monitor_volume_support_and_monitor_sources(self):
        enabled=self.device(1,'easyeffects_sink',True,enabled=True)
        self.assertTrue(audio.volume_effective(enabled,'sink'))
        monitor=self.device(2,'easyeffects_sink',True,monitor=True)
        self.assertFalse(audio.is_easyeffects(monitor))
        self.assertTrue(audio.volume_effective(self.device(3,'another_virtual_sink'),'sink'))

    def test_microphone_route_follows_links_back_to_physical_input(self):
        processor=audio.normalize(dict(index=1,name='easyeffects_source',properties={'object.id':1,'node.name':'easyeffects_source'}),'source')
        mic=audio.normalize(dict(index=3,name='Microphone',properties={'object.id':3}),'source')
        result={'sink':[], 'source':[processor,mic]}
        graph=[dict(id=1,type='PipeWire:Interface:Node',info={'props':{'node.name':'easyeffects_source','client.id':10}}),
               dict(id=2,type='PipeWire:Interface:Node',info={'props':{'node.name':'filter','client.id':10}}),
               dict(type='PipeWire:Interface:Link',info={'output-node-id':3,'input-node-id':2,'state':'active'}),
               dict(type='PipeWire:Interface:Link',info={'output-node-id':2,'input-node-id':1,'state':'active'})]
        audio.describe_processing(result,graph)
        self.assertEqual([d['name'] for d in processor['routeDevices']],['Microphone'])

    def test_ineffective_volume_is_rejected_without_changing_configuration(self):
        entry=dict(index=1,name='easyeffects_sink',properties={'monitor.channel-volumes':'false','object.serial':'5'})
        with patch.object(audio,'raw',return_value={'sinks':[entry]}), patch.object(audio,'run') as run:
            with self.assertRaisesRegex(ValueError,'final output'):
                audio.action(dict(action='volume',kind='sink',id='1',serial='5',value=80))
            run.assert_not_called()

@unittest.skipUnless(os.environ.get('WAYLAND_DISPLAY'),'Audio panel rendering needs Wayland')
class AudioPanelTests(unittest.TestCase):
    def test_all_pages_live_readonly_and_stable_models(self):
        with tempfile.TemporaryDirectory(prefix='ai-audio-panel-') as temporary:
            base=Path(temporary)
            for name in ('modules','services','assets','scripts','defaults','translations','GlobalStates.qml'):
                (base/name).symlink_to(SOURCE/name,target_is_directory=(SOURCE/name).is_dir())
            # Guard every helper mutation while permitting live state discovery.
            tools=base/'bin';tools.mkdir()
            real=shutil.which('pactl');log=base/'mutations'
            (tools/'pactl').write_text('#!/usr/bin/env python3\nimport os,sys\nfrom pathlib import Path\nif sys.argv[1:2] not in (["-f"],["subscribe"]):\n Path(os.environ["AUDIO_TEST_MUTATIONS"]).write_text(repr(sys.argv))\n sys.exit(1)\nos.execv('+repr(real)+', ['+repr(real)+',*sys.argv[1:]])\n')
            (tools/'pactl').chmod(0o755)
            (base/'shell.qml').write_text('''//@ pragma UseQApplication
import QtQuick
import Quickshell
import Quickshell.Wayland
import qs.services
import qs.modules.shared
import qs.modules.desktop.audio
ShellRoot {
    id:root
    property int phase:0
    property var first:null
    PanelWindow {
        id:host
        implicitWidth:1000;implicitHeight:700;color:Appearance.colors.colLayer0
        exclusiveZone:0;WlrLayershell.namespace:"quickshell:audio-test";WlrLayershell.layer:WlrLayer.Overlay
        WlrLayershell.keyboardFocus:WlrKeyboardFocus.None
        mask:Region{}
        AudioPanelContent{id:panel;anchors.fill:parent;anchors.margins:20}
    }
    function walk(item, callback) {
        callback(item);
        for (const child of item.children || []) walk(child, callback);
    }
    Component.onCompleted:AudioControl.open()
    Timer {
        interval:650;running:true;repeat:true
        onTriggered:{
            if(AudioControl.failed){console.error("AUDIO_FAILED",AudioControl.message);Qt.quit();return;}
            if(!AudioControl.loaded || AudioControl.busy)return;
            const pages=["playback","outputs","inputs","recording","profiles","routing","advanced"];
            let groups=null, submenus=null, defaults=null;
            walk(panel, item=>{
                if(item.objectName==="audio-main-groups")groups=item;
                if(item.objectName==="audio-subsections")submenus=item;
                if(item.objectName==="audio-device-defaults")defaults=item;
                if(item.objectName==="audio-node-card" && item.color.toString()!==Appearance.colors.colBackgroundSurfaceContainer.toString()){console.error("AUDIO_CARD_SURFACE_FAILED");Qt.quit();}
            });
            if(!groups||!submenus||submenus.y<groups.y+groups.height||defaults.visible&&defaults.y<submenus.y+submenus.height){console.error("AUDIO_NAVIGATION_ORDER_FAILED");Qt.quit();return;}
            if(root.phase===0){
                groups.activated(1);
                if(AudioControl.section!=="outputs"){console.error("AUDIO_SEGMENT_FAILED");Qt.quit();return;}
                groups.activated(0);
                submenus.activated(1);
                if(AudioControl.section!=="recording"){console.error("AUDIO_SEGMENT_FAILED");Qt.quit();return;}
                submenus.activated(0);
            }
            if(root.phase===0){
                if(AudioControl.outputs.count===0){console.error("AUDIO_NO_DEVICES");Qt.quit();return;}
                root.first=AudioControl.outputs.get(0);
            }
            walk(panel, item=>{
                if(item.objectName==="audio-node-card")item.expanded=true;
                if(item.objectName==="audio-profile-card")item.details=true;
                if(item.objectName==="audio-advanced" && AudioControl.graphObjects.length)item.selectedId=AudioControl.graphObjects[0].id;
            });
            if(root.phase<pages.length){AudioControl.section=pages[root.phase++];return;}
            if(root.phase===pages.length){AudioControl.refresh();root.phase++;return;}
            if(root.first!==AudioControl.outputs.get(0)){console.error("AUDIO_UNSTABLE_MODEL");Qt.quit();return;}
            walk(panel, item=>{
                if(item.objectName!=="audio-node-card" || item.entry.processor!=="easyeffects" || item.entry.volumeEffective!==false)return;
                let slider=null, hint=null;
                walk(item, child=>{
                    if(child.objectName==="audio-master-volume")slider=child;
                    if(child.objectName==="audio-virtual-volume-hint")hint=child;
                });
                if(!slider || slider.visible || !hint || !hint.visible){console.error("AUDIO_VIRTUAL_CONTROLS_FAILED");Qt.quit();return;}
            });
            if(root.phase===pages.length+1){
                AudioControl.section="outputs";root.phase++;
                const image=Quickshell.env("DOTS_TEST_AUDIO_IMAGE");if(image)panel.grabToImage(result=>result.saveToFile(image));
                return;
            }
            AudioControl.close();console.log("AUDIO_PANEL_OK");Qt.quit();
        }
    }
    Timer{interval:18000;running:true;onTriggered:{console.error("AUDIO_TIMEOUT",root.phase);Qt.quit();}}
}''')
            env=dict(os.environ,DOTS_SHELL_SOURCE=str(base),XDG_CONFIG_HOME=str(base/'config'),XDG_STATE_HOME=str(base/'state'),XDG_CACHE_HOME=str(base/'cache'),AUDIO_TEST_MUTATIONS=str(log),PATH=str(tools)+':'+os.environ['PATH'])
            launcher=env.get('DOTS_TEST_LAUNCHER')
            command=[launcher] if launcher else [shutil.which('quickshell'),'-p',str(base)]
            result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=25)
            logs=result.stdout+result.stderr
            self.assertEqual(result.returncode,0,logs)
            self.assertIn('AUDIO_PANEL_OK',logs)
            for failure in ('AUDIO_NAVIGATION_ORDER_FAILED','AUDIO_SEGMENT_FAILED','AUDIO_CARD_SURFACE_FAILED','TypeError:','ReferenceError:','Cannot assign','Binding loop','Unable to assign','is not defined','Required property'):
                self.assertNotIn(failure,logs)
            self.assertFalse(log.exists(),log.read_text() if log.exists() else '')
