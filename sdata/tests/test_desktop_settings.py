"""Validate desktop transactions against simulated IPC, never the user's displays."""
import importlib.util
import json
import os
import sys
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "dots/.config/quickshell/ii/scripts/hyprland/desktop.py"
spec = importlib.util.spec_from_file_location("desktop_settings", SCRIPT)
desktop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(desktop)


class DesktopSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name)
        for name, value in {
            "CONFIG": base / "config", "STATE": base / "state/artificial-impulse/desktop", "DIRECTORY": base / "config/artificial-impulse",
            "SAVED": base / "config/artificial-impulse/hyprland.json", "LUA": base / "config/artificial-impulse/hyprland.lua",
            "PENDING": base / "state/artificial-impulse/desktop/pending.json", "MAIN": base / "config/hypr/hyprland.lua",
        }.items():
            replacement = patch.object(desktop, name, value)
            replacement.start()
            self.addCleanup(replacement.stop)
        self.monitors = [dict(name="DP-1", width=2560, height=1440, refreshRate=165.0, x=0, y=0,
                              scale=1, transform=0, availableModes=["2560x1440@165.00Hz", "1920x1080@60.00Hz"]),
                         dict(name="DP-2", width=1920, height=1080, refreshRate=60.0, x=2560, y=0,
                              scale=1, transform=1, availableModes=["1920x1080@60.00Hz"])]
        for monitor in self.monitors:
            monitor["current"] = desktop.monitor_spec(monitor)
        self.live = dict(monitors=self.monitors, devices=[dict(name="keyboard", kind="keyboards"), dict(name="mouse", kind="mice")],
                         supported={key: True for key in desktop.BY_KEY},
                         values={entry["key"]: entry["default"] for entry in desktop.FIELDS})
        self.calls = []
        self.ipc_patch = patch.object(desktop, "ipc", side_effect=self.ipc)
        self.ipc_patch.start()
        self.addCleanup(self.ipc_patch.stop)

    def ipc(self, *arguments, as_json=False):
        self.calls.append(arguments)
        if arguments[:1] == ("monitors",):
            return self.monitors
        if arguments[:1] == ("devices",):
            return {"keyboards": [{"name": "keyboard"}], "mice": [{"name": "mouse"}]}
        if arguments[:1] == ("getoption",):
            entry = desktop.BY_KEY[arguments[1]]
            kind = {"bool": "bool", "int": "int", "float": "float", "gap": "css"}.get(entry["type"], "str")
            return {kind: entry["default"]}
        return ""

    def start_preview(self, changes=None):
        desktop.STATE.mkdir(parents=True, exist_ok=True)
        with patch.object(desktop, "integrated", return_value=True), patch.object(desktop, "snapshot", return_value=self.live), patch.object(desktop.subprocess, "Popen"):
            desktop.preview(changes or {"options": {"decoration:rounding": 22}})
        return desktop.read_json(desktop.PENDING)

    def test_snapshot_reads_booleans_css_and_devices_without_writes(self):
        result = desktop.snapshot()
        self.assertTrue(all(result["supported"].values()))
        self.assertIs(result["values"]["animations:enabled"], True)
        self.assertEqual(len(result["devices"]), 2)
        self.assertFalse(desktop.SAVED.exists())
        self.assertFalse(desktop.LUA.exists())
        self.assertFalse(any(call[0] in ("reload", "eval") for call in self.calls))

    def test_gradient_ipc_argb_is_converted_to_rgba_for_safe_restore(self):
        with patch.object(desktop, "ipc", return_value={"gradient": "7744464f ff123456 90deg"}):
            key, value, supported = desktop.option_value(desktop.BY_KEY["general:col:active_border"])
        self.assertTrue(supported)
        self.assertEqual(value, "rgba(44464f77) rgba(123456ff) 90deg")
        desktop.validate_value(desktop.BY_KEY[key], value)

    def test_empty_ipc_strings_are_shown_as_empty_fields(self):
        for key in ("input:kb_variant", "input:kb_options", "input:accel_profile"):
            with patch.object(desktop, "ipc", return_value={"str": "[[EMPTY]]"}):
                actual_key, value, supported = desktop.option_value(desktop.BY_KEY[key])
            self.assertTrue(supported)
            self.assertEqual(value, "")
            desktop.validate_value(desktop.BY_KEY[actual_key], value)

    def test_validate_limits_modes_and_disconnected_devices(self):
        invalid = [
            {"options": {"not:a:setting": True}}, {"options": {"general:border_size": -1}},
            {"options": {"animations:enabled": "false"}}, {"options": {"input:sensitivity": float("nan")}},
            {"options": {"input:kb_layout": 'us"); os.execute("bad")'}},
            {"options": {"input:kb_layout": ""}}, {"options": {"general:gaps_in": "5; bad"}},
            {"devices": {"unknown": {"sensitivity": 0.5}}}, {"devices": {"mouse": {"unknown": True}}},
            {"monitors": {"not-connected": self.monitors[0]["current"]}},
        ]
        for change in invalid:
            with self.subTest(change=change), self.assertRaises(ValueError):
                desktop.merge_patch(desktop.empty(), change, self.live)
        for change in [dict(mode="8000x4000@100Hz"), dict(scale=1.3), dict(scale=0), dict(transform=9), dict(x=0.5)]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                desktop.validate_monitor(dict(self.monitors[0]["current"], **change), self.monitors[0])

    def test_generate_valid_lua_and_preserve_baseline_configuration(self):
        data = desktop.merge_patch(desktop.empty(), {
            "options": {"general:gaps_in": "2 3 4 5", "input:kb_options": "grp:alt_shift_toggle", "animations:enabled": False},
            "monitors": {"DP-2": dict(self.monitors[1]["current"], x=-1080)},
            "devices": {"mouse": {"sensitivity": 0.25}},
        }, self.live)
        source = desktop.generate(data)
        self.assertIn('hl.monitor(', source)
        self.assertIn('["position"]="-1080x0"', source)
        self.assertIn('hl.device(', source)
        self.assertNotIn('require(', source)
        if shutil.which("luac"):
            path = Path(self.temporary.name) / "candidate.lua"
            path.write_text(source)
            subprocess.run(["luac", "-p", str(path)], check=True, capture_output=True)

    def test_preview_is_temporary_and_confirm_persists(self):
        pending = self.start_preview()
        self.assertFalse(desktop.SAVED.exists())
        self.assertTrue(desktop.LUA.exists())
        with self.assertRaises(ValueError):
            desktop.confirm("wrong-token")
        self.assertTrue(desktop.PENDING.exists())
        desktop.confirm(pending["token"])
        self.assertEqual(desktop.saved()["options"]["decoration:rounding"], 22)
        self.assertFalse(desktop.PENDING.exists())

    def test_revert_restores_exact_previous_managed_file_and_live_monitors(self):
        desktop.atomic(desktop.LUA, "-- previous managed file\n")
        previous = desktop.LUA.read_text()
        pending = self.start_preview({"monitors": {"DP-1": dict(self.monitors[0]["current"], scale=1.25)}})
        desktop.rollback(pending)
        self.assertEqual(desktop.LUA.read_text(), previous)
        self.assertFalse(desktop.PENDING.exists())
        self.assertFalse(desktop.SAVED.exists())
        restore = [call[1] for call in self.calls if call[0] == "eval"][-1]
        self.assertIn('["scale"]=1', restore)
        self.assertIn('["output"]="DP-2"', restore)

    def test_expired_confirmation_reverts_and_cannot_save(self):
        pending = self.start_preview()
        pending["deadline"] = time.time() - 1
        desktop.write_json(desktop.PENDING, pending)
        with self.assertRaisesRegex(ValueError, "expired"):
            desktop.confirm(pending["token"])
        self.assertFalse(desktop.LUA.exists())
        self.assertFalse(desktop.SAVED.exists())
        self.assertFalse(desktop.PENDING.exists())

    def test_new_session_restores_an_unconfirmed_preview_immediately(self):
        pending = self.start_preview()
        pending["session"] = "previous-session"
        desktop.write_json(desktop.PENDING, pending)
        with patch.dict(os.environ, HYPRLAND_INSTANCE_SIGNATURE="new-session"):
            desktop.recover_expired()
        self.assertFalse(desktop.PENDING.exists())
        self.assertFalse(desktop.LUA.exists())
        self.assertFalse((desktop.STATE / "preview-session").exists())

    @unittest.skipUnless(shutil.which("lua"), "Lua interpreter needed for loader smoke test")
    def test_loader_uses_last_good_settings_after_session_change(self):
        base = Path(self.temporary.name)
        desktop.atomic(desktop.LUA, "hl.config({fixture = 2})\n")
        desktop.atomic(desktop.STATE / "last-good.lua", "hl.config({fixture = 1})\n")
        desktop.atomic(desktop.STATE / "preview-session", "old-session\n" + str(time.time() + 1000) + "\n")
        module = ROOT / "dots/.config/hypr/hyprland/services/desktop.lua"
        script = 'hl = {config = function(value) assert(value.fixture == 1) end}; dofile(' + desktop.lua_value(str(module)) + ').load()'
        result = subprocess.run(["lua", "-e", script], capture_output=True, text=True,
            env=dict(os.environ, XDG_CONFIG_HOME=str(desktop.CONFIG), XDG_STATE_HOME=str(base / "state"), HYPRLAND_INSTANCE_SIGNATURE="new-session"))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_watchdog_restores_without_settings_process(self):
        pending = self.start_preview()
        pending["deadline"] = time.time() - 1
        desktop.write_json(desktop.PENDING, pending)
        desktop.watch(pending["token"])
        self.assertFalse(desktop.PENDING.exists())
        self.assertFalse(desktop.LUA.exists())

    def test_watchdog_retries_transient_ipc_failure(self):
        pending = self.start_preview()
        pending["deadline"] = time.time() - 1
        desktop.write_json(desktop.PENDING, pending)
        with patch.object(desktop, "rollback", side_effect=[OSError("temporary IPC failure"), None]) as rollback, patch.object(desktop.time, "sleep"):
            desktop.watch(pending["token"])
        self.assertEqual(rollback.call_count, 2)

    def test_invalid_reload_rolls_back_and_never_persists(self):
        count = 0
        original = self.ipc
        def fail_once(*arguments, **kwargs):
            nonlocal count
            if arguments == ("configerrors",):
                count += 1
                return "Invalid candidate" if count == 2 else ""
            return original(*arguments, **kwargs)
        with patch.object(desktop, "ipc", side_effect=fail_once), self.assertRaisesRegex(ValueError, "Invalid candidate"):
            self.start_preview()
        self.assertFalse(desktop.LUA.exists())
        self.assertFalse(desktop.PENDING.exists())
        self.assertFalse(desktop.SAVED.exists())

    def test_cannot_preview_without_guard_or_while_preview_pending(self):
        desktop.STATE.mkdir(parents=True, exist_ok=True)
        with patch.object(desktop, "integrated", return_value=True), patch.object(desktop, "snapshot", return_value=self.live), patch.object(desktop.subprocess, "Popen", side_effect=OSError("cannot start guard")), self.assertRaises(OSError):
            desktop.preview({"options": {"decoration:rounding": 22}})
        self.assertFalse(desktop.LUA.exists())
        self.assertFalse(desktop.PENDING.exists())
        self.start_preview()
        with patch.object(desktop, "integrated", return_value=True), self.assertRaisesRegex(ValueError, "current preview"):
            desktop.preview({"options": {"decoration:rounding": 25}})

    def test_reset_only_removes_managed_overrides(self):
        initial = desktop.empty()
        initial["options"]["general:border_size"] = 3
        initial["options"]["decoration:rounding"] = 22
        result = desktop.merge_patch(initial, {"options": {"decoration:rounding": None}}, self.live)
        self.assertEqual(result["options"], {"general:border_size": 3})
        self.assertEqual(initial["options"]["decoration:rounding"], 22)

    def test_detached_guard_restores_after_preview_command_exits(self):
        base = Path(self.temporary.name)
        tools = base / "bin"
        tools.mkdir()
        fixture = dict(monitors=self.monitors, options={entry["key"]: entry for entry in desktop.FIELDS})
        (base / "ipc-fixture.json").write_text(json.dumps(fixture))
        fake = tools / "hyprctl"
        fake.write_text("#!" + sys.executable + "\n" + """
import json, os, sys
from pathlib import Path
base = Path(os.environ['DESKTOP_FIXTURE'])
fixture = json.loads((base / 'ipc-fixture.json').read_text())
args = sys.argv[1:]
with (base / 'ipc-calls.jsonl').open('a') as target: target.write(json.dumps(args) + '\\n')
if args[0] == 'monitors': print(json.dumps(fixture['monitors']))
elif args[0] == 'devices': print('{"mice": [], "keyboards": []}')
elif args[0] == 'getoption':
    entry = fixture['options'][args[1]]
    kind = {'bool':'bool', 'int':'int', 'float':'float', 'gap':'css'}.get(entry['type'], 'str')
    print(json.dumps({kind: entry['default']}))
elif args[0] == 'configerrors': print('')
else: print('ok')
""")
        fake.chmod(0o755)
        desktop.MAIN.parent.mkdir(parents=True)
        desktop.MAIN.write_text(desktop.HOOK + "\n")
        module = desktop.CONFIG / "hypr/hyprland/services/desktop.lua"
        module.parent.mkdir(parents=True)
        module.write_text("-- fixture integration\n")
        environment = dict(os.environ, XDG_CONFIG_HOME=str(desktop.CONFIG),
                           XDG_STATE_HOME=str(base / "xdg-state"),
                           PATH=str(tools) + os.pathsep + os.environ["PATH"], DESKTOP_FIXTURE=str(base))
        bootstrap = "import importlib.util,sys; s=importlib.util.spec_from_file_location('fixture_desktop',sys.argv[1]); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); m.TIMEOUT=0.5; sys.argv=['desktop.py','preview']; m.main()"
        result = subprocess.run([sys.executable, "-c", bootstrap, str(SCRIPT)],
                                input=json.dumps({"options": {"decoration:rounding": 22}}),
                                capture_output=True, text=True, env=environment, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["ok"])
        pending = base / "xdg-state/artificial-impulse/desktop/pending.json"
        deadline = time.monotonic() + 6
        while pending.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertFalse(pending.exists(), "Detached guard did not restore the pending preview")
        self.assertFalse(desktop.LUA.exists())
        self.assertFalse(desktop.SAVED.exists())
        calls = [json.loads(line) for line in (base / "ipc-calls.jsonl").read_text().splitlines()]
        self.assertTrue(any(call[0] == "eval" for call in calls), "Runtime baseline was not restored")

    def test_install_adds_only_loader_and_creates_backup(self):
        desktop.MAIN.parent.mkdir(parents=True)
        original = '-- my settings\nhl.config({ general = { gaps_in = 9 } })\n'
        desktop.MAIN.write_text(original)
        result = desktop.install()
        self.assertTrue(desktop.integrated())
        self.assertTrue(desktop.MAIN.read_text().startswith(original.rstrip()))
        self.assertEqual((Path(result["backup"]) / "hyprland.lua").read_text(), original)
        before = desktop.MAIN.read_text()
        desktop.install()
        self.assertEqual(desktop.MAIN.read_text(), before)
