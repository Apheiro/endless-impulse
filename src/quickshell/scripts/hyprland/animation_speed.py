#!/usr/bin/env python3
"""Scale compositor animations without editing the user's Hyprland configuration."""
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys


def same_animation(current, previous):
    return (all(current.get(key) == previous.get(key) for key in ('name', 'enabled', 'bezier', 'spring', 'style'))
            and abs(current['speed'] - previous.get('speed', -1)) < 0.011)


def plan(animations, previous, factor, durations=None):
    """Keep unscaled baselines, rebasing individual animations changed externally."""
    if not math.isfinite(factor) or not 0.25 <= factor <= 3:
        raise ValueError('Animation speed must be between 0.25 and 3')
    durations = {} if durations is None else durations
    if not isinstance(durations, dict) or any(isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not 10 <= value <= 10000 for value in durations.values()):
        raise ValueError('Individual animation durations must be between 10 and 10000 ms')
    commands, state = [], {}
    for row in animations:
        name = row.get('name', '')
        if not row.get('overridden') or name.startswith('__') or not name:
            continue
        current = {key: row[key] for key in ('name', 'enabled', 'speed', 'bezier', 'spring', 'style') if key in row}
        old = previous.get(name, {})
        baseline = old['baseline'] if old.get('applied') and same_animation(current, old['applied']) else current
        duration = durations.get(name, baseline['speed'] * 100)
        applied = dict(baseline, speed=max(0.01, round(duration / 100 / factor, 4)))
        # Explicitly disabled animations stay disabled; inherited branches stay inherited.
        fields = {'leaf': name, 'enabled': applied['enabled'], 'speed': applied['speed']}
        for key in ('bezier', 'spring', 'style'):
            if applied.get(key):
                fields[key] = applied[key]
        spec = ','.join(key + '=' + (str(value).lower() if isinstance(value, bool) else json.dumps(value))
                        for key, value in fields.items())
        if not same_animation(current, applied):
            commands.append('hl.animation({' + spec + '})')
        state[name] = {'baseline': baseline, 'applied': applied}
    return commands, state


def sync(factor, durations=None, read_only=False):
    signature = os.environ.get('HYPRLAND_INSTANCE_SIGNATURE')
    if not signature:
        return {"animations": []}
    runtime = Path(os.environ.get('XDG_RUNTIME_DIR', '/run/user/' + str(os.getuid()))) / 'endless-Impulse'
    runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
    identity = hashlib.sha256(signature.encode()).hexdigest()[:20]
    path = runtime / ('animation-speed-' + identity + '.json')
    with path.with_suffix('.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            previous = json.loads(path.read_text())
        except (FileNotFoundError, ValueError):
            previous = {}
        result = subprocess.run(['hyprctl', 'animations', '-j'], check=True, capture_output=True, text=True, timeout=5)
        animations = json.loads(result.stdout)[0]
        commands, state = plan(animations, previous, factor, durations)
        catalog = {"animations": sorted([{"name": name, "duration": round(value["baseline"]["speed"] * 100),
                    "enabled": value["baseline"]["enabled"]} for name, value in state.items()], key=lambda row: row["name"])}
        if read_only:
            return catalog
        if commands:
            result = subprocess.run(['hyprctl', 'eval', ';'.join(commands)], check=True,
                                    capture_output=True, text=True, timeout=5)
            if result.stdout.strip() not in ('', 'ok'):
                raise RuntimeError(result.stdout.strip())
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(state))
        temporary.replace(path)
        return catalog


if __name__ == '__main__':
    try:
        print(json.dumps(sync(1 if sys.argv[1] == "--list" else float(sys.argv[1]),
                              json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}, sys.argv[1] == "--list")))
    except (ValueError, OSError, subprocess.SubprocessError, RuntimeError) as error:
        print('Could not synchronize Hyprland animation speed: ' + str(error), file=sys.stderr)
        sys.exit(1)
