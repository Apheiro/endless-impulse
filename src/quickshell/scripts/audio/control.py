#!/usr/bin/env python3
"""PipeWire desktop audio control using its native graph and Pulse compatibility API."""
import concurrent.futures
import json
import math
import subprocess
import sys

KINDS={'sink':'sinks','source':'sources','sink-input':'sink_inputs','source-output':'source_outputs','card':'cards'}


def run(args, json_output=False):
    try:
        result=subprocess.run(args,capture_output=True,text=True,timeout=8)
    except FileNotFoundError as error:
        raise ValueError(f'{args[0]} is not installed.') from error
    if result.returncode:
        raise ValueError(result.stderr.strip() or f'{args[0]} could not complete the request.')
    return json.loads(result.stdout) if json_output else result.stdout.strip()


def raw():
    return run(['pactl','-f','json','list'],True)


def rows(value):
    if isinstance(value,dict): return [dict(item,name=name) for name,item in value.items()]
    return value or []


def serial(entry):
    return str(entry.get('properties',{}).get('object.serial',entry['index']))


def normalize(entry,kind,default=''):
    props=entry.get('properties',{})
    channels=[]
    order=entry.get('channel_map','').split(',')
    volume=entry.get('volume',{})
    for channel in order if order!=[''] else volume:
        data=volume.get(channel,{})
        channels.append(dict(name=channel,volume=round(data.get('value',0)/65536*100,2),db=data.get('db','')))
    name=props.get('application.name') if kind in ('sink-input','source-output') else entry.get('description')
    ports=rows(entry.get('ports',[]))
    return dict(id=str(entry['index']),serial=serial(entry),kind=kind,name=name or entry.get('name') or props.get('node.name') or str(entry['index']),
                technicalName=entry.get('name',''),media=props.get('media.name',''),
                icon=props.get('application.icon_name',props.get('application.icon-name',props.get('device.icon_name',''))),
                pwId=int(props.get('object.id',-1)),volume=max([c['volume'] for c in channels],default=0),channels=channels,
                muted=entry.get('mute',False),state=entry.get('state',''),format=entry.get('sample_specification',''),
                default=bool(default and entry.get('name')==default),monitor=bool(entry.get('monitor_of_sink') not in (None,4294967295,'4294967295') or entry.get('name','').endswith('.monitor')),
                target=str(entry.get('sink',entry.get('source',''))),ports=[dict(name=p['name'],label=p.get('description',p['name']),available=p.get('availability',p.get('available','unknown'))) for p in ports],
                activePort=entry.get('active_port',''),properties=props,
                latency=entry.get('latency',{}),baseVolume=entry.get('base_volume',{}).get('value_percent',''))


def is_easyeffects(entry):
    props = entry.get('properties', {})
    if entry.get('monitor') or entry.get('name', entry.get('technicalName', '')).endswith('.monitor'):
        return False
    return (props.get('application.id') == 'com.github.wwmm.easyeffects'
            or props.get('node.name', entry.get('name', '')) in ('easyeffects_sink', 'easyeffects_source'))


def volume_effective(entry, kind):
    # EasyEffects reads the monitor without applying the virtual sink's channel volumes.
    value = entry.get('properties', {}).get('monitor.channel-volumes')
    return not (kind == 'sink' and is_easyeffects(entry) and str(value).lower() == 'false')


def describe_processing(result, graph):
    """Derive final devices from existing links; never assume they follow the default."""
    nodes = {str(obj['id']): obj.get('info', {}).get('props', {})
             for obj in graph if obj.get('type', '').endswith(':Node')}
    clients = {str(props['client.id']) for props in nodes.values()
               if 'client.id' in props and is_easyeffects({'properties': props})}
    owned = {identity for identity, props in nodes.items()
             if is_easyeffects({'properties': props})
             or str(props.get('client.id', '')) in clients}
    forward = {}; backward = {}
    for obj in graph:
        info = obj.get('info', {})
        if not obj.get('type', '').endswith(':Link') or info.get('state') in ('error', 'unlinked'):
            continue
        source = str(info.get('output-node-id', ''))
        target = str(info.get('input-node-id', ''))
        forward.setdefault(source, set()).add(target)
        backward.setdefault(target, set()).add(source)
    for kind in ('sink', 'source'):
        devices = result[kind]
        destinations = {str(item['pwId']): item for item in devices if not is_easyeffects(item)}
        for entry in devices:
            entry['processor'] = 'easyeffects' if is_easyeffects(entry) else ''
            entry['volumeEffective'] = volume_effective(entry, kind)
            entry['routeDevices'] = []
            if not entry['processor']:
                continue
            edges = forward if kind == 'sink' else backward
            pending = [str(entry['pwId'])]; visited = set(); found = set()
            while pending:
                node = pending.pop()
                if node in visited:
                    continue
                visited.add(node)
                if node in destinations:
                    found.add(node)
                elif node in owned:
                    pending.extend(edges.get(node, ()))
            entry['routeDevices'] = [dict(id=item['id'], serial=item['serial'], kind=kind, name=item['name'])
                                     for item in devices if str(item['pwId']) in found]


def snapshot():
    jobs=[(['pactl','-f','json','list'],True),(['pactl','-f','json','info'],True),(['pw-dump'],True)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results=list(pool.map(lambda item:run(*item),jobs))
    pulse,info,graph=results
    result={kind:[normalize(entry,kind,info.get('default_sink_name' if kind=='sink' else 'default_source_name','') if kind in ('sink','source') else '') for entry in pulse.get(key,[])] for kind,key in KINDS.items() if kind!='card'}
    describe_processing(result, graph)
    cards=[]
    for entry in pulse.get('cards',[]):
        props=entry.get('properties',{})
        profiles=rows(entry.get('profiles',{}))
        cards.append(dict(id=str(entry['index']),serial=serial(entry),name=props.get('device.description',entry.get('name','')),technicalName=entry.get('name',''),
                          activeProfile=entry.get('active_profile',''),profiles=[dict(name=p['name'],label=p.get('description',p['name']),available=p.get('available','unknown')) for p in profiles],
                          ports=[dict(name=p['name'],label=p.get('description',p['name']),latency=int(str(p.get('latency_offset',0)).split()[0]),available=p.get('availability',p.get('available','unknown'))) for p in rows(entry.get('ports',[]))],properties=props))
    nodes={};ports=[];links=[];metadata={};objects=[]
    for obj in graph:
        kind=obj.get('type','').split(':')[-1]
        data=obj.get('info',{})
        props=data.get('props',obj.get('props',{}))
        if kind=='Node': nodes[obj['id']]=props
        if kind=='Metadata' and props.get('metadata.name')=='settings': metadata={entry['key']:entry.get('value') for entry in obj.get('metadata',[]) if entry.get('subject')==0}
        objects.append(dict(id=str(obj['id']),serial=str(props.get('object.serial',obj['id'])),type=kind,
                            name=props.get('node.description',props.get('application.name',props.get('node.name',props.get('device.description',props.get('metadata.name',props.get('port.name',str(obj['id']))))))),
                            properties=props,state=data.get('state',''),params=data.get('params',{})))
    by_port={}
    for obj in graph:
        kind=obj.get('type','').split(':')[-1];data=obj.get('info',{});props=data.get('props',{})
        if kind=='Port':
            node=nodes.get(int(props.get('node.id',-1)),{})
            item=dict(id=str(obj['id']),serial=str(props.get('object.serial',obj['id'])),nodeId=str(props.get('node.id','')),direction=data.get('direction',props.get('port.direction','')),
                      name=props.get('port.alias',props.get('port.name',str(obj['id']))),nodeName=node.get('node.description',node.get('node.name','')),
                      media=props.get('format.dsp',''),channel=props.get('audio.channel',''),properties=props)
            by_port[obj['id']]=item;ports.append(item)
        elif kind=='Link':
            links.append(dict(id=str(obj['id']),serial=str(props.get('object.serial',obj['id'])),output=str(data.get('output-port-id',props.get('link.output.port',''))),input=str(data.get('input-port-id',props.get('link.input.port',''))),state=data.get('state','')))
    for link in links:
        link['outputName']=by_port.get(int(link['output']),{}).get('name',link['output'])
        link['inputName']=by_port.get(int(link['input']),{}).get('name',link['input'])
    result.update(cards=cards,ports=ports,links=links,objects=objects,clock=metadata,
                  server=dict(name=info.get('server_name',''),version=info.get('server_version',''),format=info.get('default_sample_specification','')))
    return result


def number(value,minimum,maximum):
    if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value) or not minimum<=value<=maximum:
        raise ValueError(f'Enter a value between {minimum} and {maximum}.')
    return value


def find(data,kind,identity,token):
    if kind not in KINDS: raise ValueError('Unknown audio object type.')
    entry=next((entry for entry in data.get(KINDS[kind],[]) if str(entry['index'])==str(identity)),None)
    if not entry or serial(entry)!=str(token): raise ValueError('This audio object changed or disconnected. Refresh and try again.')
    return entry


def graph_object(graph,identity,token,kind):
    entry=next((obj for obj in graph if str(obj['id'])==str(identity) and obj.get('type','').endswith(':'+kind)),None)
    if not entry or str(entry.get('info',{}).get('props',{}).get('object.serial',entry['id']))!=str(token):
        raise ValueError('This PipeWire object changed or disconnected.')
    return entry


def action(payload):
    op=payload.get('action');kind=payload.get('kind');identity=payload.get('id');token=payload.get('serial')
    if op == 'adjust-default':
        steps = number(payload.get('steps'), -1000, 1000)
        if int(steps) != steps: raise ValueError('Volume steps must be whole numbers.')
        limit = number(payload.get('limit', 100), 0, 100)
        info = run(['pactl', '-f', 'json', 'info'], True)
        entry = next((item for item in raw().get('sinks', []) if item.get('name') == info.get('default_sink_name')), None)
        if not entry: raise ValueError('No default audio output is connected.')
        value = normalize(entry, 'sink')['volume']
        for _ in range(abs(int(steps))):
            value = max(0, min(limit, value + (1 if value < 10 else 2) * (1 if steps > 0 else -1)))
        # Revalidate identity using the same mutation path as panel sliders.
        action(dict(action='volume', kind='sink', id=str(entry['index']), serial=serial(entry), value=value))
        return
    if op in ('connect','disconnect'):
        graph=run(['pw-dump'],True)
        if op=='disconnect':
            link=graph_object(graph,identity,token,'Link');run(['pw-link','-d',str(link['id'])])
        else:
            output=graph_object(graph,payload.get('output'),payload.get('outputSerial'),'Port')
            input_=graph_object(graph,payload.get('input'),payload.get('inputSerial'),'Port')
            if output.get('info',{}).get('direction')!='out' or input_.get('info',{}).get('direction')!='in': raise ValueError('Connect an output port to an input port.')
            args=['pw-link']
            if payload.get('passive'): args+=['-P']
            run([*args,str(output['id']),str(input_['id'])])
        return
    if op=='clock':
        key=payload.get('key');value=number(payload.get('value'),0,768000 if key=='clock.force-rate' else 8192)
        if key not in ('clock.force-rate','clock.force-quantum') or int(value)!=value: raise ValueError('Unknown PipeWire clock option.')
        if value and key=='clock.force-rate' and value<8000: raise ValueError('The sample rate must be at least 8000 Hz, or 0 for automatic.')
        if value and key=='clock.force-quantum' and value<16: raise ValueError('The quantum must be at least 16 frames, or 0 for automatic.')
        run(['pw-metadata','-n','settings','0',key,str(int(value))]);return
    data=raw();entry=find(data,kind,identity,token)
    if op=='volume':
        if not volume_effective(entry, kind): raise ValueError('EasyEffects bypasses this virtual volume. Adjust the final output device instead.')
        if kind=='card': raise ValueError('Cards do not have a volume control.')
        values=payload.get('values')
        if values is not None:
            if not isinstance(values,list) or len(values)!=len(entry.get('volume',{})): raise ValueError('The channel layout changed. Refresh first.')
        else: values=[payload.get('value')]
        values=[f'{number(value,0,200):.2f}%' for value in values]
        run(['pactl',f'set-{kind}-volume',str(entry['index']),*values])
    elif op=='mute':
        if kind=='card' or not isinstance(payload.get('value'),bool): raise ValueError('Invalid mute request.')
        run(['pactl',f'set-{kind}-mute',str(entry['index']),'1' if payload['value'] else '0'])
    elif op=='default':
        if kind not in ('sink','source'): raise ValueError('Only devices can be the default.')
        run(['pactl',f'set-default-{kind}',entry['name']])
    elif op=='move':
        if kind not in ('sink-input','source-output'): raise ValueError('Select an application stream.')
        destination=find(data,'sink' if kind=='sink-input' else 'source',payload.get('target'),payload.get('targetSerial'))
        run(['pactl',f'move-{kind}',str(entry['index']),str(destination['index'])])
    elif op=='port':
        if kind not in ('sink','source'): raise ValueError('Only devices have ports.')
        available=rows(entry.get('ports',[]));port=next((p for p in available if p['name']==payload.get('value')),None)
        if not port or port.get('availability',port.get('available'))=='no': raise ValueError('This port is unavailable.')
        run(['pactl',f'set-{kind}-port',str(entry['index']),port['name']])
    elif op=='profile':
        if kind!='card': raise ValueError('Select an audio card.')
        profile=next((p for p in rows(entry.get('profiles',{})) if p['name']==payload.get('value')),None)
        if not profile or profile.get('available')=='no': raise ValueError('This profile is unavailable.')
        run(['pactl','set-card-profile',str(entry['index']),profile['name']])
    elif op=='latency':
        if kind!='card' or not any(p['name']==payload.get('port') for p in rows(entry.get('ports',[]))): raise ValueError('Select a card port.')
        value=number(payload.get('value'),-5000000,5000000)
        run(['pactl','set-port-latency-offset',str(entry['index']),payload['port'],str(int(value))])
    else: raise ValueError('Unknown audio action.')


def main():
    try:
        if len(sys.argv)>1 and sys.argv[1]=='action': action(json.load(sys.stdin));result={}
        else: result=snapshot()
        result['ok']=True
    except (ValueError,KeyError,TypeError,subprocess.SubprocessError,OSError) as error:
        result=dict(ok=False,error=str(error))
    print(json.dumps(result));return 0 if result['ok'] else 1


if __name__=='__main__':sys.exit(main())
