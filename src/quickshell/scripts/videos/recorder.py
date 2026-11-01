#!/usr/bin/env python3
"""GPU Screen Recorder settings and session supervisor; never signals unrelated processes."""
import contextlib
import datetime as dt
import fcntl
import json
import math
import locale
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import uuid

CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'artificial-impulse'
STATE = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'artificial-impulse/recorder'
STORE = CONFIG / 'recorder.json'
SESSION = STATE / 'session.json'
SESSION_ID = os.environ.get('HYPRLAND_INSTANCE_SIGNATURE', os.environ.get('WAYLAND_DISPLAY', ''))
FIELDS = []
try:
    locale.setlocale(locale.LC_TIME, "")
except locale.Error:
    pass


def field(key, label, group, default, flag='', choices=None, minimum=None, maximum=None, kind=None, hint=''):
    FIELDS.append(dict(key=key, label=label, group=group, default=default, flag=flag, choices=choices or [],
                       minimum=minimum, maximum=maximum, type=kind or ('enum' if choices else 'bool' if isinstance(default, bool) else 'int' if isinstance(default, int) else 'text'), hint=hint))


field('mode', 'Session type', 'Files', 'record', choices=['record', 'replay', 'stream', 'audio'])
field('saveDirectory', 'Save directory', 'Files', str(Path.home() / 'Videos'))
field('directoryPattern', 'Date-based subfolders', 'Files', '', hint='%Y/%m/%d · %A (weekday) · %B (month)')
field('filenamePattern', 'Filename pattern', 'Files', 'recording_%Y-%m-%d_%H.%M.%S', hint='%Y-%m-%d · %A · %H-%M-%S · %f (microseconds). Extension is added automatically.')
field('container', 'Container', 'Files', 'mp4', '-c', ['mp4', 'mkv', 'mov', 'webm', 'flv', 'ts', 'm3u8', 'whip', 'mp3'])
field('fps', 'Frames per second', 'Video', 60, '-f', minimum=1, maximum=1000)
field('codec', 'Video codec', 'Video', 'auto', '-k', ['auto', 'h264', 'hevc', 'av1', 'vp8', 'vp9', 'hevc_hdr', 'av1_hdr', 'hevc_10bit', 'av1_10bit', 'h264_vulkan', 'hevc_vulkan', 'hevc_hdr_vulkan', 'hevc_10bit_vulkan', 'av1_vulkan', 'av1_hdr_vulkan', 'av1_10bit_vulkan'])
field('quality', 'Quality', 'Video', 'very_high', '-q', ['medium', 'high', 'very_high', 'ultra'])
field('bitrateMode', 'Bitrate mode', 'Video', 'auto', '-bm', ['auto', 'qp', 'vbr', 'cbr'])
field('bitrateKbps', 'Video bitrate (CBR, kbps)', 'Video', 20000, minimum=1, maximum=1000000)
field('frameRateMode', 'Frame pacing', 'Video', 'vfr', '-fm', ['vfr', 'cfr', 'content'])
field('resolution', 'Resolution limit', 'Video', '0x0', '-s', hint='0x0 = original · 1920x1080 keeps the original aspect ratio')
field('cursor', 'Record cursor', 'Video', True, '-cursor')
field('audioTracks', 'Audio tracks (one track per line)', 'Audio', ['default_output'], '-a', kind='lines', hint='default_output | default_input mixes both into one track. Separate lines create separate tracks. app:firefox · app-inverse:firefox · device:name')
field('audioCodec', 'Audio codec', 'Audio', '', '-ac', ['', 'aac', 'opus', 'mp3', 'flac'])
field('audioBitrate', 'Audio bitrate (kbps, 0 = automatic)', 'Audio', 0, '-ab', minimum=0, maximum=100000)
field('defaultTarget', 'Default recording target', 'Capture', 'region', choices=['region', 'fullscreen', 'configured'])
field('captureSource', 'Custom capture source', 'Capture', '', '-w', hint='Empty = focused monitor · portal · /dev/video0 · DP-1|/dev/video0;halign=end;valign=end;width=30%;height=30%;hflip=true')
field('customRegion', 'Custom region', 'Capture', '', '-region', hint='WIDTHxHEIGHT+X+Y, in desktop coordinates. Used with custom source region.')
field('restorePortal', 'Restore portal session', 'Capture', False, '-restore-portal-session')
field('portalTokenFile', 'Portal session token file', 'Capture', '', '-portal-session-token-filepath')
field('replaySeconds', 'Replay duration (seconds)', 'Replay & streaming', 60, '-r', minimum=2, maximum=86400)
field('replayStorage', 'Replay storage', 'Replay & streaming', 'ram', '-replay-storage', ['ram', 'disk'])
field('restartReplay', 'Clear replay buffer after saving', 'Replay & streaming', False, '-restart-replay-on-save')
field('replayDateFolders', 'GPU Screen Recorder replay date folders', 'Replay & streaming', False, '-df')
field('parallelDirectory', 'Parallel recording directory', 'Replay & streaming', '', '-ro', hint='Optional, for replay and streaming sessions')
field('streamUrl', 'Streaming destination', 'Replay & streaming', '', hint='rtmp://… · srt://… · https://…/whip')
field('authToken', 'Streaming authentication', 'Replay & streaming', '', '-auth', kind='password', hint='Passed through GSR_AUTH, never added to the command line')
field('encoder', 'Encoder', 'Encoding & color', 'gpu', '-encoder', ['gpu', 'cpu'])
field('fallbackCpu', 'Allow CPU fallback', 'Encoding & color', False, '-fallback-cpu-encoding')
field('colorRange', 'Color range', 'Encoding & color', 'limited', '-cr', ['limited', 'full'])
field('tune', 'Encoder tuning', 'Encoding & color', 'performance', '-tune', ['performance', 'quality'])
field('keyint', 'Keyframe interval (seconds)', 'Encoding & color', '2.0', '-keyint', kind='float', minimum=0.01, maximum=3600)
field('lowPower', 'Low-power encoding (AMD)', 'Encoding & color', False, '-low-power')
field('excludeMetadata', 'Exclude personal metadata', 'Advanced', False, '-exclude-metadata')
field('writeTimestamp', 'Keep first-frame timestamp file', 'Advanced', False, '-write-first-frame-ts')
field('plugins', 'Overlay plugins (one .so path per line)', 'Advanced', [], '-p', kind='lines')
field('saveScript', 'Script to run after saving', 'Advanced', '', '-sc')
field('ffmpegOptions', 'FFmpeg muxer options', 'Advanced', '', '-ffmpeg-opts', hint='key=value;key=value')
field('ffmpegVideoOptions', 'FFmpeg video options', 'Advanced', '', '-ffmpeg-video-opts', hint='key=value;key=value')
field('ffmpegAudioOptions', 'FFmpeg audio options', 'Advanced', '', '-ffmpeg-audio-opts', hint='key=value;key=value')
field('verbose', 'FPS and damage logging', 'Advanced', False, '-v')
field('glDebug', 'OpenGL debug logging', 'Advanced', False, '-gl-debug')


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.recording-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, indent=2)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def load(path, default):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return default


def settings():
    result = {f['key']: f['default'] for f in FIELDS}
    legacy = load(CONFIG / 'config.json', {}).get('screenRecord', {}).get('savePath')
    if legacy: result['saveDirectory'] = legacy
    result.update(load(STORE, {}))
    return result


def validate(values):
    result = {}
    for f in FIELDS:
        value = values.get(f['key'], f['default'])
        if f['type'] == 'bool' and not isinstance(value, bool): raise ValueError(f"{f['label']}: choose yes or no.")
        if f['type'] == 'enum' and value not in f['choices']: raise ValueError(f"{f['label']}: invalid choice.")
        if f['type'] in ('int', 'float'):
            try: number = float(value)
            except (ValueError, TypeError): raise ValueError(f"{f['label']}: enter a number.")
            if isinstance(value, bool) or not math.isfinite(number) or not f['minimum'] <= number <= f['maximum'] or (f['type'] == 'int' and int(number) != number):
                raise ValueError(f"{f['label']}: enter a value between {f['minimum']} and {f['maximum']}.")
            value = int(number) if f['type'] == 'int' else str(number)
        if f['type'] == 'lines':
            if not isinstance(value, list) or any(not isinstance(v, str) or '\0' in v for v in value): raise ValueError(f"{f['label']}: invalid list.")
            value = [v.strip() for v in value if v.strip()]
        elif f['type'] in ('text', 'password') and (not isinstance(value, str) or '\0' in value or '\n' in value):
            raise ValueError(f"{f['label']}: invalid text.")
        result[f['key']] = value
    if not re.fullmatch(r'\d+x\d+', result['resolution']): raise ValueError('Resolution must look like 1920x1080 or 0x0.')
    width, height = map(int, result['resolution'].split('x'))
    if (width == 0) != (height == 0) or max(width, height) > 32768: raise ValueError('Invalid output resolution.')
    if not result['saveDirectory'] or not Path(result['saveDirectory']).expanduser().is_absolute(): raise ValueError('Choose an absolute save directory.')
    output_path(result)  # Validate date patterns without creating directories.
    return result


def formatted(pattern, now):
    if any(c in pattern for c in ('\0', '\n', '\r')): raise ValueError('Invalid date pattern.')
    # Reject unknown strftime directives, which Python otherwise silently leaves intact.
    if re.search(r'%(?![%aAbBcdDeFgGhHIjmMnprRStTuUVwWxXyYzZfCs+])', pattern): raise ValueError('Unknown date token. Use %Y, %m, %d, %A, %H, %M, %S or %f.')
    value = now.strftime(pattern)
    if any(ord(c) < 32 for c in value): raise ValueError("Date patterns cannot contain control characters.")
    return value


def output_path(config, now=None):
    now = now or dt.datetime.now().astimezone()
    subfolder = formatted(config['directoryPattern'], now)
    filename = formatted(config['filenamePattern'], now)
    if Path(subfolder).is_absolute() or '..' in Path(subfolder).parts: raise ValueError('Date subfolders must stay inside the save directory.')
    if not filename or filename in ('.', '..') or '/' in filename: raise ValueError('The filename pattern must produce a filename, without folders.')
    extension = config['container']
    if filename.lower().endswith('.' + extension): filename = filename[:-(len(extension) + 1)]
    return Path(config['saveDirectory']).expanduser() / subfolder / (filename + '.' + extension)


def binary():
    override = os.environ.get('DOTS_GSR_BINARY')
    candidates = [override] if override else ['/run/wrappers/bin/gpu-screen-recorder', '/usr/bin/gpu-screen-recorder', shutil.which('gpu-screen-recorder')]
    for candidate in candidates:
        if candidate and os.access(candidate, os.X_OK): return str(Path(candidate).absolute())
    raise ValueError('GPU Screen Recorder is not installed. Install gpu-screen-recorder.')


def recorder_environment(executable):
    environment = dict(os.environ)
    if executable.startswith(('/usr/', '/run/wrappers/')):
        for name in ('LD_LIBRARY_PATH','__EGL_VENDOR_LIBRARY_FILENAMES','__EGL_EXTERNAL_PLATFORM_CONFIG_DIRS','GBM_BACKENDS_PATH','LIBGL_DRIVERS_PATH'):
            environment.pop(name, None)
    return environment


def query(executable, *args):
    try:
        result = subprocess.run([executable, *args], capture_output=True, text=True, timeout=8, env=recorder_environment(executable))
        return result.stdout.strip() if result.returncode == 0 or (args == ('--help',) and result.stdout.startswith('usage:')) else ''
    except (OSError, subprocess.TimeoutExpired): return ''


def capabilities():
    try: executable = binary()
    except ValueError as error: return dict(installed=False, error=str(error), flags=[], version='', codecs=[], containers=[], capture=[], audio=[], applications=[], cameras=[])
    help_text = query(executable, '--help')
    info = query(executable, '--info')
    sections, section = {}, ''
    for line in info.splitlines():
        if line.startswith('section='): section = line.split('=', 1)[1]; sections[section] = []
        elif section: sections[section].append(line)
    def pairs(text):
        return [dict(id=line.split('|')[0], name=line.partition('|')[2] or line) for line in text.splitlines() if line]
    flags = list(dict.fromkeys(re.findall(r'(?<!\w)-[a-z][a-z-]*', help_text)))
    return dict(installed=True, executable=executable, version=query(executable, '--version'), flags=flags,
                codecs=sections.get('video_codecs', []), containers=sections.get('containers', []),
                capture=pairs('\n'.join(sections.get('capture_options', []))), audio=pairs(query(executable, '--list-audio-devices')),
                applications=pairs(query(executable, '--list-application-audio')), cameras=pairs(query(executable, '--list-v4l2-devices')))


def process_token(pid):
    try: return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
    except (OSError, IndexError): return None


def status():
    state = load(SESSION, {})
    if state.get('session') != SESSION_ID: return dict(active=False, phase='idle')
    if state.get('active') and process_token(state.get('supervisor', 0)) != state.get('supervisorToken'):
        state.update(active=False, phase='error', error='The recording supervisor exited unexpectedly. Check the recording log.')
    state['elapsed'] = max(0, time.monotonic() - state.get('monotonicStart', time.monotonic()) - state.get('pausedTotal', 0) - (time.monotonic() - state.get('pausedAt', time.monotonic()) if state.get('paused') else 0))
    return state


@contextlib.contextmanager
def locked():
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / 'control.lock').open('w') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def monitors():
    result = subprocess.run(['hyprctl', 'monitors', '-j'], capture_output=True, text=True, timeout=4, check=True)
    return json.loads(result.stdout)


def region_from(value):
    if isinstance(value, str):
        match = re.fullmatch(r'(-?\d+),(-?\d+) (\d+)x(\d+)', value.strip())
        if not match: raise ValueError('Invalid selected region.')
        x, y, width, height = map(int, match.groups())
    elif isinstance(value, dict):
        x, y, width, height = [value.get(key) for key in ('x', 'y', 'width', 'height')]
        if any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in (x, y, width, height)): raise ValueError('Invalid selected region.')
        x, y, width, height = [round(v) for v in (x, y, width, height)]
    else: raise ValueError('Select a region first.')
    if width < 2 or height < 2: raise ValueError('The recording region must be at least 2×2 pixels.')
    return dict(x=x, y=y, width=width, height=height)


def command(config, context, caps, destination, ipc_path):
    args = [caps['executable']]
    target = context.get('target', 'fullscreen')
    source = context.get('monitor', '')
    region = None
    if target == 'configured': source = config['captureSource'] or source
    if target == 'region':
        region = region_from(context.get('region'))
        source = 'region'
    if config['mode'] != 'audio':
        if not source: raise ValueError('No capture source is available.')
        args += ['-w', source]
        if region:
            args += ['-region', f"{region['width']}x{region['height']}+{region['x']}+{region['y']}"]
        elif source == 'region':
            if not re.fullmatch(r'\d+x\d+\+-?\d+\+-?\d+', config['customRegion']): raise ValueError('Set a custom region or select one interactively.')
            args += ['-region', config['customRegion']]
            match = re.fullmatch(r'(\d+)x(\d+)\+(-?\d+)\+(-?\d+)', config['customRegion'])
            width, height, x, y = map(int, match.groups()); region = region_from(dict(x=x,y=y,width=width,height=height))
    tracks = config['audioTracks'] or (['default_output'] if context.get('sound') else [])
    if config['mode'] == 'audio' and not tracks: raise ValueError('Audio-only recording needs at least one audio source.')
    if config['mode'] == 'audio' and config['container'] not in ('mp3', 'mkv', 'mp4', 'webm'): raise ValueError('Choose an audio-compatible container.')
    if config['mode'] != 'audio' and config['container'] == 'mp3': raise ValueError('MP3 is available in audio-only mode.')
    if config['mode'] != 'audio' and config['container'] == 'webm' and config['codec'] not in ('vp8', 'vp9', 'av1', 'av1_10bit'): raise ValueError('WebM needs VP8, VP9 or AV1. Choose MKV/MP4 for H.264 or HEVC.')
    if config['mode'] != 'audio' and config['encoder'] == 'cpu' and config['codec'] not in ('auto', 'h264'): raise ValueError('CPU encoding supports H.264 only.')
    if caps.get('codecs') and config['codec'] != 'auto' and config['mode'] != 'audio' and config['codec'] not in caps['codecs']: raise ValueError('This video codec is not supported by the current GPU/driver.')
    if config['mode'] != 'audio' and config['frameRateMode'] == 'content' and source != 'portal' and os.environ.get('WAYLAND_DISPLAY'): raise ValueError('Content frame pacing on Wayland requires portal capture.')
    if config['mode'] != 'audio' and '_hdr' in config['codec'] and source == 'portal': raise ValueError('HDR recording requires direct monitor/region capture.')
    flags = caps['flags']
    def option(flag, value, optional=False):
        if flag not in flags:
            if optional: return
            raise ValueError(f'Installed GPU Screen Recorder does not support {flag}. Update it or reset that option.')
        args.extend([flag, str(value)])
    replay = config['mode'] == 'replay'
    skip = {'-w','-region','-o','-auth','-ipc','-write-first-frame-ts','-a','-q','-r','-ro','-df','-replay-storage','-restart-replay-on-save'}
    audio_flags = {'-ac', '-ab'}
    for f in FIELDS:
        flag = f['flag']; value = config[f['key']]
        if not flag or flag in skip or (config['mode'] == 'audio' and flag not in audio_flags | {'-c','-sc','-v','-gl-debug','-exclude-metadata','-ffmpeg-opts','-ffmpeg-audio-opts'}): continue
        if value == '' or value == [] or (flag in audio_flags and not tracks): continue
        if f['type'] == 'bool': value = 'yes' if value else 'no'
        if f['type'] == 'lines':
            for item in value: option(flag, item)
        else: option(flag, value, optional=config[f['key']] == f['default'])
    if config['mode'] != 'audio': option('-q', config['bitrateKbps'] if config['bitrateMode'] == 'cbr' else config['quality'])
    for track in tracks: option('-a', track)
    if replay:
        for flag, value in [('-r', config['replaySeconds']), ('-replay-storage', config['replayStorage']), ('-restart-replay-on-save', 'yes' if config['restartReplay'] else 'no'), ('-df', 'yes' if config['replayDateFolders'] else 'no')]: option(flag, value)
    if config['mode'] in ('replay', 'stream') and config['parallelDirectory']:
        option('-ro', str(Path(config['parallelDirectory']).expanduser()))
    option('-ipc', str(ipc_path), optional=True)
    if config['mode'] in ('record', 'audio'): option('-write-first-frame-ts', 'yes', optional=True)
    option('-o', str(destination)) if '-o' in flags else args.extend(['-o', str(destination)])
    return args, region


def ipc(state, name, data=None):
    path = state.get('socket')
    if not path or not Path(path).exists(): return None
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(20 if name == 'stop' else 5)
        client.connect(path)
        client.sendall((json.dumps(dict(id=1, name=name, data=data)) + '\n').encode())
        response = b''
        while b'\n' not in response and len(response) < 1024 * 1024:
            chunk = client.recv(4096)
            if not chunk: break
            response += chunk
        reply = json.loads(response)
        if reply.get('result') != 'ok': raise ValueError(reply.get('data', 'Recording command failed.'))
        return reply


def control(action):
    with locked():
        state = status()
        if not state.get('active'): return state
        if state.get('phase') == 'starting' and action != 'stop': raise ValueError('Wait until capture starts.')
        pid = state.get('pid')
        if not pid or process_token(pid) != state.get('pidToken'):
            if action == 'stop': state.update(cancelled=True); atomic(SESSION, state); return state
            raise ValueError('The recorder process is not available.')
        if action == 'pause' and state.get('mode') not in ('record', 'audio'): raise ValueError('Replay/stream sessions cannot be paused.')
        if action == 'save-replay' and state.get('mode') != 'replay': raise ValueError('No replay buffer is active.')
        if action == 'parallel' and state.get('mode') not in ('replay', 'stream'): raise ValueError('Parallel recording needs a replay or streaming session.')
        name = {'stop':'stop', 'pause':'set-paused', 'save-replay':'save-replay', 'parallel':'toggle-replay-recording'}[action]
        pause = not state.get('paused', False)
        reply = ipc(state, name, pause if action == 'pause' else None)
        if reply is None:
            signals = {'stop':signal.SIGINT, 'pause':signal.SIGUSR2, 'save-replay':signal.SIGUSR1, 'parallel':signal.SIGRTMIN}
            os.kill(pid, signals[action])
        if action == 'pause':
            if state.get('mode') not in ('record', 'audio'): raise ValueError('Replay/stream sessions cannot be paused.')
            if pause: state['pausedAt'] = time.monotonic()
            else: state['pausedTotal'] = state.get('pausedTotal', 0) + time.monotonic() - state.get('pausedAt', time.monotonic())
            state['paused'] = pause
        elif action == 'stop': state['phase'] = 'stopping'
        if reply and isinstance(reply.get('data'), str): state['lastSaved'] = reply['data']
        atomic(SESSION, state)
        return state


def start(context):
    config = validate(settings())
    caps = capabilities()
    if not caps['installed']: raise ValueError(caps['error'])
    if config['mode'] != 'audio' and context.get('target') == 'region' and not context.get('region'):
        result = subprocess.run(['slurp'], capture_output=True, text=True)
        if result.returncode: return dict(active=False, phase='idle')
        context['region'] = region_from(result.stdout)
    if config['mode'] != 'audio' and not context.get('monitor'):
        displays = monitors()
        focused = next((m for m in displays if m.get('focused')), displays[0] if displays else None)
        if focused: context['monitor'] = focused['name']
    path = output_path(config)
    destination = config['streamUrl'] if config['mode'] == 'stream' else path.parent if config['mode'] == 'replay' else path
    if config['mode'] == 'stream' and not re.match(r'^(?:rtmps?|https?|srt|udp|tcp)://', str(destination)): raise ValueError('Set a valid streaming destination.')
    token = uuid.uuid4().hex
    socket_dir = Path(os.environ.get('XDG_RUNTIME_DIR', '/tmp')) / ('artificial-recorder-' + str(os.getuid()))
    socket_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    socket_path = socket_dir / (token[:12] + '.sock')
    args, region = command(config, context, caps, destination, socket_path)
    if region:
        displays = monitors()
        def contains(m):
            width, height = m['width'], m['height']
            if m.get('transform', 0) % 2: width, height = height, width
            width /= m.get('scale', 1); height /= m.get('scale', 1)
            return region['x'] >= m['x'] and region['y'] >= m['y'] and region['x'] + region['width'] <= m['x'] + width + 1 and region['y'] + region['height'] <= m['y'] + height + 1
        selected = next((m for m in displays if contains(m)), None)
        if not selected: raise ValueError('Select a region contained within a single monitor.')
        region.update(monitor=selected['name'], monitorX=selected['x'], monitorY=selected['y'])
    with locked():
        if status().get('active'): raise ValueError('A recording session is already running.')
        if config['mode'] != 'stream':
            Path(destination if config['mode'] == 'replay' else Path(destination).parent).mkdir(parents=True, exist_ok=True)
            if config['mode'] != 'replay':
                candidate = Path(destination)
                number = 1
                while candidate.exists(): candidate = path.with_name(path.stem + '-' + str(number) + path.suffix); number += 1
                destination = candidate
                args[args.index('-o') + 1] = str(destination)
        if config['mode'] in ('replay', 'stream') and config['parallelDirectory']: Path(config['parallelDirectory']).expanduser().mkdir(parents=True, exist_ok=True)
        request = STATE / (token + '.json')
        plan = dict(token=token, args=args, region=region, output=str(destination) if config['mode'] != 'stream' else '', mode=config['mode'], socket=str(socket_path), session=SESSION_ID,
                    keepTimestamp=config['writeTimestamp'], auth=config['authToken'])
        atomic(request, plan)
        with (STATE / 'supervisor.log').open('w') as supervisor_log:
            os.chmod(STATE / 'supervisor.log', 0o600)
            process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), 'supervise', str(request)], start_new_session=True, stdin=subprocess.DEVNULL, stdout=supervisor_log, stderr=supervisor_log)
        state = dict(active=True, phase='starting', supervisor=process.pid, supervisorToken=process_token(process.pid), token=token, session=SESSION_ID, mode=config['mode'], region=region, output=plan['output'], socket=str(socket_path), paused=False, pausedTotal=0)
        atomic(SESSION, state)
    return state


def supervise(request):
    plan = load(request, {})
    Path(request).unlink(missing_ok=True)
    log = STATE / 'recording.log'
    environment = recorder_environment(plan['args'][0])
    if plan['auth']: environment['GSR_AUTH'] = plan['auth']
    process = None
    try:
        with log.open('w') as stream:
            os.chmod(log, 0o600)
            process = subprocess.Popen(plan['args'], env=environment, stdin=subprocess.DEVNULL, stdout=stream, stderr=stream)
            with locked():
                state = load(SESSION, {})
                if state.get('token') != plan['token']: process.send_signal(signal.SIGINT); return
                state.update(pid=process.pid, pidToken=process_token(process.pid), log=str(log))
                atomic(SESSION, state)
            timestamp = Path(plan['output'] + '.ts') if plan['output'] else None
            began = time.monotonic()
            ready = False
            while process.poll() is None:
                time.sleep(0.15)
                with locked():
                    state = load(SESSION, {})
                    if state.get('token') != plan['token']: break
                    if state.get('cancelled'): process.send_signal(signal.SIGINT); state['phase'] = 'stopping'
                    first_frame = timestamp and timestamp.exists()
                    socket_ready = Path(plan['socket']).exists() and time.monotonic() - began > 1
                    if not ready and (first_frame or (plan['mode'] in ('replay', 'stream', 'audio') and socket_ready) or ('-write-first-frame-ts' not in plan['args'] and time.monotonic() - began > 2)):
                        ready = True
                        state.update(phase='recording', startedAt=time.time()*1000, monotonicStart=time.monotonic())
                        if first_frame and not plan['keepTimestamp']: timestamp.unlink(missing_ok=True)
                        atomic(SESSION, state)
            code = process.wait()
        with locked():
            state = load(SESSION, {})
            if state.get('token') == plan['token']:
                error = '' if code == 0 else '\n'.join(log.read_text(errors='replace').splitlines()[-8:])
                state.update(active=False, phase='idle' if code == 0 else 'error', error=error, exitCode=code)
                if plan['output'] and Path(plan['output']).is_file() and code == 0: state['lastSaved'] = plan['output']
                atomic(SESSION, state)
    except Exception as error:
        if process and process.poll() is None: process.send_signal(signal.SIGINT)
        with locked():
            state = load(SESSION, {})
            if state.get('token') == plan['token']: state.update(active=False, phase='error', error=str(error)); atomic(SESSION, state)
    finally:
        Path(plan['socket']).unlink(missing_ok=True)


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else 'status'
    if action == 'supervise': supervise(sys.argv[2]); return 0
    try:
        if action == 'snapshot':
            with locked():
                if not SESSION.exists(): atomic(SESSION, dict(active=False, phase='idle', session=SESSION_ID))
            caps = capabilities(); config = settings()
            fields = [dict(f, supported=not f['flag'] or f['flag'] in caps['flags'] or f['key'] == 'authToken') for f in FIELDS]
            result = dict(settings=config, capabilities=caps, fields=fields, status=status(), preview=str(output_path(config)), store=str(STORE), storeExists=STORE.exists(), statePath=str(STATE))
        elif action == 'save':
            config = validate(json.load(sys.stdin)); atomic(STORE, config)
            result = dict(settings=config, storeExists=True, preview=str(output_path(config)), message='Recording preferences saved.')
        elif action == 'preview': result = dict(preview=str(output_path(validate(json.load(sys.stdin)))))
        elif action == 'start': result = dict(status=start(json.load(sys.stdin)))
        elif action in ('stop','pause','save-replay','parallel'): result = dict(status=control(action))
        elif action == 'status': result = dict(status=status())
        elif action == 'toggle':
            if status().get('active'): result = dict(status=control('stop'))
            else:
                args = sys.argv[2:]; context = dict(target='fullscreen' if '--fullscreen' in args else 'region', sound='--sound' in args)
                if '--region' in args: context['region'] = region_from(args[args.index('--region') + 1])
                result = dict(status=start(context))
        else: raise ValueError('Unknown recording command.')
        result['ok'] = True
    except Exception as error: result = dict(ok=False, error=str(error))
    print(json.dumps(result))
    return 0 if result['ok'] else 1


if __name__ == '__main__': sys.exit(main())
