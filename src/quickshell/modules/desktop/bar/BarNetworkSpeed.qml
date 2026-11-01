import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import Quickshell.Io
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets

RowLayout {
    id:root
    property var previous:({})
    property double sampledAt:0
    property real download:0
    property real upload:0
    spacing:4
    function format(rate){return rate>=1048576?(rate/1048576).toFixed(1)+" MB/s":(rate/1024).toFixed(0)+" KB/s";}
    FileView {
        id:counters;path:"/proc/net/dev"
        onLoaded:{
            const now=Date.now(), next={};let rx=0,tx=0;
            for(const line of text().split("\n")){
                const pieces=line.trim().split(/[:\s]+/);if(pieces.length<17||pieces[0]==="lo")continue;
                const name=pieces[0], sample={rx:Number(pieces[1]),tx:Number(pieces[9])};next[name]=sample;
                if(root.previous[name]){rx+=Math.max(0,sample.rx-root.previous[name].rx);tx+=Math.max(0,sample.tx-root.previous[name].tx);}
            }
            if(root.sampledAt){const elapsed=(now-root.sampledAt)/1000;root.download=rx/elapsed;root.upload=tx/elapsed;}
            root.previous=next;root.sampledAt=now;
        }
    }
    Timer{interval:1500;running:root.visible;repeat:true;onTriggered:counters.reload()}
    MaterialSymbol{text:"network_check";iconSize:18;color:Appearance.colors.colPrimary}
    StyledText{text:"↓ "+root.format(root.download)+"  ↑ "+root.format(root.upload);font.pixelSize:Appearance.font.pixelSize.smaller;color:Appearance.colors.colOnLayer0}
}
