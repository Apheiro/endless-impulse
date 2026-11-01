"""Render the actual tint on colored/shaded/transparent pixels and compare Color blend."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'src/quickshell'


def color_blend(rgb,tint):
    original=[v/255 for v in rgb]
    color=[v/255 for v in tint[:3]]
    lum=lambda c:sum(a*b for a,b in zip(c,(.30,.59,.11)))
    light=lum(original)
    color=[c+light-lum(color) for c in color]
    low,high=min(color),max(color)
    if low<0:color=[light+(c-light)*light/(light-low) for c in color]
    if high>1:color=[light+(c-light)*(1-light)/(high-light) for c in color]
    amount=tint[3]/255
    return tuple(round(255*(a*(1-amount)+b*amount)) for a,b in zip(original,color))


@unittest.skipUnless(os.environ.get('WAYLAND_DISPLAY'),'Tint rendering needs Wayland')
class TrayTintTests(unittest.TestCase):
    def test_color_blend_preserves_luminosity_alpha_and_live_changes(self):
        with tempfile.TemporaryDirectory(prefix='ai-tray-tint-') as temporary:
            base=Path(temporary)
            for name in ('modules','services','assets','scripts','defaults','translations','GlobalStates.qml'):
                (base/name).symlink_to(SOURCE/name,target_is_directory=(SOURCE/name).is_dir())
            pixels=[(0,0,0,255),(35,35,35,255),(128,128,128,255),(235,235,235,255),(255,255,255,255),
                    (225,35,60,255),(25,190,60,255),(20,65,220,255),(160,90,40,128),(255,0,0,0)]
            picture=Image.new('RGBA',(len(pixels)*20,20))
            for i,pixel in enumerate(pixels):picture.paste(pixel,(i*20,0,(i+1)*20,20))
            picture.save(base/'icon.png')
            (base/'shell.qml').write_text('''//@ pragma UseQApplication
import QtQuick
import Quickshell
import Quickshell.Wayland
import qs.modules.shared.widgets
import qs.modules.shared.primitives.common
import qs.modules.shared.primitives.settings
import qs.modules.shared.primitives.dialogs
ShellRoot {
    id:root
    property int phase:0
    PanelWindow {
        id:host
        implicitWidth:200;implicitHeight:20;exclusiveZone:0;color:"transparent"
        WlrLayershell.namespace:"quickshell:tint-test";WlrLayershell.keyboardFocus:WlrKeyboardFocus.None
        mask:Region{}
        Image{id:original;anchors.fill:parent;source:Qt.resolvedUrl("icon.png");visible:false;smooth:false}
        ColorTint{id:effect;anchors.fill:parent;source:original;tintColor:"#12b873"}
    }
    Timer {
        interval:350;running:true;repeat:true
        onTriggered:{
            if(original.status!==Image.Ready)return;
            if(root.phase===0){
                effect.grabToImage(result=>result.saveToFile(Quickshell.shellPath("green.png")));
                root.phase++;
            }else if(root.phase===1){effect.tintColor="#aa365bde";root.phase++;}
            else if(root.phase===2){effect.grabToImage(result=>result.saveToFile(Quickshell.shellPath("blue.png")));root.phase++;}
            else if(root.phase===3){effect.tintColor="transparent";root.phase++;}
            else if(root.phase===4){effect.grabToImage(result=>result.saveToFile(Quickshell.shellPath("original.png")));root.phase++;}
            else{console.log("TRAY_TINT_OK");Qt.quit();}
        }
    }
}''')
            env=dict(os.environ,DOTS_SHELL_SOURCE=str(base),XDG_CONFIG_HOME=str(base/'config'),XDG_STATE_HOME=str(base/'state'),XDG_CACHE_HOME=str(base/'cache'))
            launcher=env.get('DOTS_TEST_LAUNCHER')
            command=[launcher] if launcher else [shutil.which('quickshell'),'-p',str(base)]
            result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=10)
            logs=result.stdout+result.stderr
            self.assertEqual(result.returncode,0,logs)
            self.assertIn('TRAY_TINT_OK',logs)
            for failure in ('TypeError:','ReferenceError:','Cannot assign','Failed to','shader compilation failed'):
                self.assertNotIn(failure,logs)
            for filename,tint in [('green.png',(18,184,115,255)),('blue.png',(54,91,222,170)),('original.png',(0,0,0,0))]:
                with Image.open(base/filename).convert('RGBA') as rendered:
                    for i,pixel in enumerate(pixels):
                        actual=rendered.getpixel((i*20+10,10))
                        self.assertLessEqual(abs(actual[3]-pixel[3]),1,(filename,pixel,actual))
                        if pixel[3]==0:continue
                        expected=color_blend(pixel[:3],tint)
                        for a,b in zip(actual[:3],expected):self.assertLessEqual(abs(a-b),4,(filename,pixel,actual,expected))
                    # Export only an opt-in preview; tests otherwise leave no user files.
                    output=os.environ.get('DOTS_TEST_TINT_IMAGE')
                    if output and filename=='green.png':rendered.save(output)
