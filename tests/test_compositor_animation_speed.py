"""Compositor speed preserves animation style, inheritance and unscaled baselines."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'src/quickshell/scripts/hyprland/animation_speed.py'
spec = importlib.util.spec_from_file_location('animation_speed', SCRIPT)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def row(name='layersIn', speed=2.7, **overrides):
    return dict(name=name, speed=speed, enabled=True, overridden=True, bezier='ease', style='slide right', **overrides)


def applied_rows(state):
    return [dict(value['applied'], overridden=True) for value in state.values()]


class CompositorAnimationSpeedTests(unittest.TestCase):
    def test_global_factor_and_repeat_without_compounding(self):
        original = [row(), row('windowsIn', 3), row('workspaces', 7)]
        commands, state = helper.plan(original, {}, 2)
        self.assertEqual(len(commands), 3)
        self.assertEqual(state['layersIn']['applied']['speed'], 1.35)
        self.assertIn('style="slide right"', commands[0])
        commands, unchanged = helper.plan(applied_rows(state), state, 2)
        self.assertEqual(commands, [])
        self.assertEqual(unchanged, state)
        _, faster = helper.plan(applied_rows(state), state, 3)
        self.assertEqual(faster['layersIn']['applied']['speed'], 0.9)
        _, restored = helper.plan(applied_rows(faster), faster, 1)
        self.assertEqual(restored['layersIn']['applied']['speed'], 2.7)

    def test_reload_external_edits_and_rounded_ipc(self):
        original = [row()]
        _, state = helper.plan(original, {}, 1.4)
        observed = applied_rows(state)
        observed[0]['speed'] = round(observed[0]['speed'], 2)
        _, next_state = helper.plan(observed, state, 2)
        self.assertEqual(next_state['layersIn']['baseline']['speed'], 2.7)
        _, after_reload = helper.plan(original, state, 2)
        self.assertEqual(after_reload['layersIn']['applied']['speed'], 1.35)
        _, edited = helper.plan([row(speed=4.2)], state, 2)
        self.assertEqual(edited['layersIn']['applied']['speed'], 2.1)

    def test_individual_duration_then_reset_preserves_original(self):
        _, state = helper.plan([row()], {}, 2, {'layersIn': 800})
        self.assertEqual(state['layersIn']['applied']['speed'], 4)
        self.assertEqual(state['layersIn']['baseline']['speed'], 2.7)
        _, faster = helper.plan(applied_rows(state), state, 3, {'layersIn': 800})
        self.assertAlmostEqual(faster['layersIn']['applied']['speed'], 2.6667)
        _, restored = helper.plan(applied_rows(faster), faster, 1, {})
        self.assertEqual(restored['layersIn']['applied']['speed'], 2.7)
        for durations in ({'layersIn': 0}, {'layersIn': float('nan')}, {'layersIn': True}, []):
            with self.assertRaises(ValueError): helper.plan([row()], {}, 1, durations)

    def test_inheritance_disabled_and_internal_animations(self):
        animations = [row(), dict(row('layersOut'), overridden=False),
                      dict(row('borderangle'), enabled=False), row('__internal_fadeCTM')]
        commands, state = helper.plan(animations, {}, 2)
        self.assertEqual(set(state), {'layersIn', 'borderangle'})
        self.assertIn('enabled=false', commands[1])
        self.assertNotIn('layersOut', ''.join(commands))
        for factor in (0, -1, 4, float('nan'), float('inf')):
            with self.assertRaises(ValueError): helper.plan(animations, {}, factor)

    def test_baseline_survives_helper_restart(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            (base / 'hyprctl').write_text('''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
if sys.argv[1]=='animations': print(Path(os.environ['ANIMATION_TEST_ROWS']).read_text())
else: print('ok')
''')
            (base / 'hyprctl').chmod(0o755)
            rows = base / 'rows.json'
            rows.write_text(json.dumps([[row()], []]))
            env = dict(os.environ, PATH=str(base) + os.pathsep + os.environ['PATH'],
                       XDG_RUNTIME_DIR=str(base), HYPRLAND_INSTANCE_SIGNATURE='animation-speed-test', ANIMATION_TEST_ROWS=str(rows))
            subprocess.run([sys.executable, str(SCRIPT), '2'], env=env, check=True, capture_output=True)
            state_file = next((base / 'artificial-impulse').glob('*.json'))
            state = json.loads(state_file.read_text())
            rows.write_text(json.dumps([applied_rows(state), []]))
            subprocess.run([sys.executable, str(SCRIPT), '3'], env=env, check=True, capture_output=True)
            state = json.loads(state_file.read_text())
            self.assertEqual(state['layersIn']['applied']['speed'], 0.9)
            self.assertEqual(state['layersIn']['baseline']['speed'], 2.7)
