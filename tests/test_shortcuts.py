"""Run with: python3 -m unittest discover -s tests -v"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "shortcuts", ROOT / "src/quickshell/scripts/hyprland/shortcuts.py")
shortcuts = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(shortcuts)


class ShortcutTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        shortcuts.CONFIG = self.base / "config/endless-Impulse"
        shortcuts.STATE = self.base / "state/endless-Impulse"
        shortcuts.STORE = shortcuts.CONFIG / "shortcuts.lua"
        shortcuts.CONFIG.mkdir(parents=True)
        self.entries = [
            {"id": "|SUPER+E", "default": "SUPER + E", "submap": "", "description": "Files"},
            {"id": "|SUPER+T", "default": "SUPER + T", "submap": "", "description": "Terminal"},
        ]

    def test_validation_and_aliases(self):
        self.assertEqual(shortcuts.normalize("control + win + Return"), "SUPER + CTRL + Return")
        self.assertEqual(shortcuts.normalize("SUPER + mouse:272"), "SUPER + mouse:272")
        for value in ("", "SUPER +", "SUPER + SUPER + E", "BOGUS + E", "SUPER + $(touch bad)", "NoSuchKey"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                shortcuts.normalize(value)

    def test_conflicts_include_aliases_and_submap_universal(self):
        with self.assertRaisesRegex(ValueError, "already used"):
            shortcuts.update("set", "|SUPER+E", "MOD4 + t", self.entries, {})
        self.entries[1].update(submap="vm", universal=True)
        with self.assertRaisesRegex(ValueError, "already used"):
            shortcuts.update("set", "|SUPER+E", "SUPER + T", self.entries, {})

    def test_save_restore_and_separate_submaps(self):
        self.entries[1]["submap"] = "vm"
        overrides = {}
        with patch.object(shortcuts, "run_hyprctl", return_value=""):
            shortcuts.update("set", "|SUPER+E", "SUPER + T", self.entries, overrides)
            self.assertEqual(shortcuts.read_overrides(), {"|SUPER+E": "SUPER + T"})
            shortcuts.update("reset", "|SUPER+E", "", self.entries, overrides)
        self.assertEqual(shortcuts.read_overrides(), {})

    def test_reload_error_rolls_back(self):
        shortcuts.save({"|SUPER+E": "SUPER + F8"})
        previous = shortcuts.STORE.read_bytes()
        with patch.object(shortcuts, "run_hyprctl", side_effect=["ok", "Invalid binding", "ok"]):
            with self.assertRaisesRegex(ValueError, "rolled back"):
                shortcuts.update("set", "|SUPER+E", "SUPER + F9", self.entries, {})
        self.assertEqual(shortcuts.STORE.read_bytes(), previous)

    def test_restore_preserves_intentional_default_overlaps(self):
        self.entries[1].update(default="E", ignore_mods=True)
        overrides = {"|SUPER+E": "SUPER + F9"}
        with patch.object(shortcuts, "run_hyprctl", return_value=""):
            shortcuts.update("reset", "|SUPER+E", "", self.entries, overrides)
        self.assertEqual(shortcuts.read_overrides(), {})

    def test_external_storage_is_not_overwritten(self):
        shortcuts.STORE.write_text("return { custom = true }\n")
        with self.assertRaisesRegex(ValueError, "edited externally"):
            shortcuts.read_overrides()

    def test_list_reports_storage_without_creating_an_override_file(self):
        with patch.object(shortcuts, "catalog", return_value=self.entries), patch.object(shortcuts.sys, "argv", ["shortcuts.py", "list"]):
            result = shortcuts.main()
        self.assertEqual(result["store"], str(shortcuts.STORE))
        self.assertEqual(result["directory"], str(shortcuts.CONFIG))
        self.assertFalse(result["storeExists"])
        self.assertFalse(shortcuts.STORE.exists())

    def test_full_lua_catalog_and_linked_actions(self):
        # Execute the real keybind definitions with inert dispatchers, never the desktop.
        harness = r'''
local root = arg[1]
HOME = os.getenv("HOME")
is_file_exists = function() return false end
local proxy = {}
setmetatable(proxy, { __index = function() return proxy end, __call = function() return function() end end })
local count, remapped = 0, 0
local original = function(keys, dispatcher, options)
    count = count + 1
    assert(type(dispatcher) == "function")
    if keys == "SUPER + F9" then remapped = remapped + 1 end
    return count
end
hl = { dsp = proxy, env = function() end, bind = original,
       define_submap = function(name, callback) callback() end }
require = function() return {} end
dofile(root .. "/config/xdg/config/hypr/hyprland/variables.lua")
local shortcuts = dofile(root .. "/config/xdg/config/hypr/hyprland/services/shortcuts.lua")
shortcuts.start()
dofile(root .. "/config/xdg/config/hypr/hyprland/keybinds.lua")
shortcuts.finish()
assert(hl.bind == original)
print(count, remapped)
'''
        env = dict(os.environ, XDG_CONFIG_HOME=str(self.base / "config"), XDG_STATE_HOME=str(self.base / "state"))

        def execute():
            return subprocess.run(["lua", "-", str(ROOT)], input=harness, text=True, env=env,
                                  capture_output=True, check=True).stdout.split()

        first = execute()
        entries = shortcuts.catalog()
        self.assertGreater(len(entries), 100)
        for trigger, category in [("SUPER + T", "App"), ("SUPER + code:10", "Workspace"),
                                  ("XF86AudioRaiseVolume", "Media"), ("XF86MonBrightnessUp", "Screen")]:
            entry = next(entry for entry in entries if entry["default"] == trigger)
            self.assertEqual(entry["category"], category)
        self.assertTrue(all(entry["category"] for entry in entries))
        for entry in entries:
            with self.subTest(shortcut=entry["default"]):
                shortcuts.normalize(entry["default"])
        self.assertEqual(sum(entry["count"] for entry in entries), int(first[0]))
        selected = next(entry for entry in entries if entry["default"] == "SUPER + SHIFT + S")
        self.assertEqual(selected["count"], 2)
        shortcuts.save({selected["id"]: "SUPER + F9"})
        second = execute()
        self.assertEqual(first[0], second[0])
        self.assertEqual(int(second[1]), 2)
        self.assertTrue(any(e["submap"] == "virtual-machine" and e["universal"] for e in entries))


if __name__ == "__main__":
    unittest.main()
