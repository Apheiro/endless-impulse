"""Hardware V1: fake sysfs, real JSON CLI and draft-only security boundaries."""
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src/quickshell/scripts/hardware"
sys.path.insert(0, str(BACKEND))
from inventory import Inventory, parse_udev, public_properties
from rules import DraftStore, preview, validate


def rule(**kwargs):
    # Fixture IDs, deliberately unrelated to any host device.
    return dict(id="fixture-device", label="Fixture", subsystem="hidraw", kernel="hidraw*",
                vendor="abcd", product="0123", uaccess=True, enabled=True, mode="", group="", **kwargs)


class HardwareTests(unittest.TestCase):
    def test_udev_database_parsing_and_privacy(self):
        records = parse_udev("P: /devices/pci0/usb1/1-2\nE: ID_MODEL=Test=Device\nE: ID_SERIAL=secret\nE: ID_SERIAL_SHORT=secret\nE: ID_WWN=secret\nE: ID_FS_UUID=secret\nE: HID_UNIQ=secret\nE: DEVLINKS=/dev/disk/by-id/serial-secret\n\nP: /devices/virtual/net/lo\nE: SUBSYSTEM=net\n\n")
        self.assertEqual(len(records), 2)
        clean = public_properties(records["/devices/pci0/usb1/1-2"])
        self.assertEqual(clean, {"ID_MODEL": "Test=Device"})

    def test_real_sysfs_fixture_tree_and_driver(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            usb = root / "devices/pci0000:00/0000:00:01.0/usb1/1-2"
            interface = usb / "1-2:1.0"
            hidraw = interface / "0003:ABCD:0123.0001/hidraw/hidraw7"
            for path, subsystem in ((usb, "usb"), (interface, "usb"), (hidraw, "hidraw")):
                path.mkdir(parents=True, exist_ok=True)
                bus = root / "bus" / subsystem
                (bus / "devices").mkdir(parents=True, exist_ok=True)
                (bus / "devices" / path.name).symlink_to(path)
                (path / "subsystem").symlink_to(bus)
                (path / "uevent").write_text("DEVTYPE=usb_device\n")
            (usb / "idVendor").write_text("abcd\n")
            (usb / "idProduct").write_text("0123\n")
            (usb / "product").write_text("Fixture device\n")
            (usb / "serial").write_text("DO-NOT-EXPOSE")
            driver = root / "bus/usb/drivers/usbhid"
            driver.mkdir(parents=True)
            module = root / "module/usbhid"
            (module / "parameters").mkdir(parents=True)
            (module / "parameters/poll").write_text("4")
            (module / "initstate").write_text("live")
            (driver / "module").symlink_to(module)
            (interface / "driver").symlink_to(driver)
            inventory = Inventory(root, use_tools=False)
            snapshot = inventory.snapshot()
            devices = {d["id"]: d for d in snapshot["devices"]}
            identity = "/" + str(hidraw.relative_to(root))
            interface_id = "/" + str(interface.relative_to(root))
            self.assertEqual(devices[interface_id]["kind"], "interface")
            self.assertEqual(devices[identity]["kind"], "interface")
            self.assertIn(devices[identity]["parent"], devices)
            self.assertEqual(devices[identity]["physicalId"], "/" + str(usb.relative_to(root)))
            detail = inventory.detail(identity)
            self.assertTrue(detail["ruleSupported"])
            self.assertEqual(detail["usbSelector"]["vendor"], "abcd")
            self.assertEqual(detail["usbSelector"]["product"], "0123")
            driver_detail = inventory.detail(interface_id)
            self.assertFalse(driver_detail["ruleSupported"])
            self.assertEqual(driver_detail["module"], "usbhid")
            self.assertEqual(driver_detail["parameters"], {"poll": "4"})
            self.assertEqual(driver_detail["binding"], "bound")
            self.assertNotIn("DO-NOT-EXPOSE", json.dumps([snapshot, detail, driver_detail]))
            (interface / "driver").unlink()
            self.assertEqual(inventory.detail(interface_id)["binding"], "unbound-or-not-applicable")
            for bad in ("../../etc", "/devices/../../etc", "/module/usbhid", "/devices/missing"):
                with self.assertRaises(ValueError): inventory.detail(bad)
            (root / "devices/escape").symlink_to("/etc")
            with self.assertRaises(ValueError): inventory.detail("/devices/escape")

    def test_rules_precise_output_and_allowlist(self):
        result = preview(rule())
        self.assertEqual(result["filename"], "70-endless-impulse-fixture-device.rules")
        self.assertIn('SUBSYSTEM=="hidraw", KERNEL=="hidraw*", ATTRS{idVendor}=="abcd", ATTRS{idProduct}=="0123", TAG+="uaccess"', result["content"])
        self.assertFalse(result["activeOnHost"])
        usb = {**rule(), "subsystem": "usb", "kernel": "1-2"}
        self.assertIn('ATTR{idVendor}', preview(usb)["content"])
        for changes in ({"id": "../../escape"}, {"id": "a\nRUN=x"}, {"vendor": "*"}, {"product": ""},
                        {"kernel": "*"}, {"kernel": 'hidraw*", RUN+="evil'}, {"mode": "0666"},
                        {"group": "$(id)"}, {"group": "nonexistent-fixture-group-xyz"}, {"RUN": "true"},
                        {"subsystem": "block"}, {"uaccess": "true"}, {"enabled": 1}, {"uaccess": False}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate({**rule(), **changes})

    def test_draft_crud_backup_restore_and_symlink_rejection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "hardware"
            store = DraftStore(root)
            self.assertEqual(store.list(), [])
            store.mutate("save", rule())
            self.assertEqual(len(store.list()), 1)
            self.assertEqual((root / "drafts.json").stat().st_mode & 0o777, 0o600)
            store.mutate("save", {**rule(), "enabled": False, "mode": "0660"})
            self.assertFalse(store.list()[0]["rule"]["enabled"])
            store.mutate("restore", None)
            self.assertTrue(store.list()[0]["rule"]["enabled"])
            store.mutate("delete", "fixture-device")
            self.assertEqual(store.list(), [])
            before = (root / "drafts.json").read_bytes()
            with self.assertRaises(ValueError): store.mutate("save", {**rule(), "id": "../bad"})
            self.assertEqual((root / "drafts.json").read_bytes(), before)
            (root / "drafts.json").unlink()
            target = Path(temp) / "untouched"
            target.write_text("original")
            (root / "drafts.json").symlink_to(target)
            with self.assertRaises(ValueError): store.mutate("save", rule())
            self.assertEqual(target.read_text(), "original")
            self.assertFalse(list(root.glob("*.rules")))

    def test_atomic_failure_keeps_previous_drafts(self):
        with tempfile.TemporaryDirectory() as temp:
            store = DraftStore(Path(temp) / "hardware")
            store.mutate("save", rule())
            original = store._write
            def fail(name, rules):
                if name == "drafts.json": raise OSError("fixture write failure")
                return original(name, rules)
            with patch.object(store, "_write", side_effect=fail), self.assertRaises(OSError):
                store.mutate("delete", "fixture-device")
            self.assertEqual(len(store.list()), 1)
            self.assertEqual(json.loads((store.root / "previous.json").read_text())["rules"], [validate(rule())])

    def test_malformed_metadata_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "hardware"
            root.mkdir()
            store = DraftStore(root)
            for content in ("[]", "{", '{"version":1,"rules":[{}]}', '{"version":2,"rules":[]}'):
                path = root / "drafts.json"
                path.write_text(content)
                with self.assertRaises(ValueError): store.mutate("save", rule())
                self.assertEqual(path.read_text(), content)
            path.unlink()
            os.mkfifo(path)
            with self.assertRaises(ValueError): store.list()

    @unittest.skipUnless(shutil.which("udevadm"), "udevadm not available")
    def test_generated_rules_with_real_udev_verifier(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            variants = [("hidraw", "hidraw*"), ("input", "event*"), ("tty", "ttyACM*"), ("usb", "1-2.3")]
            for subsystem, kernel in variants:
                generated = preview({**rule(), "subsystem": subsystem, "kernel": kernel, "mode": "0660"})
                path = base / generated["filename"]
                path.write_text(generated["content"])
                result = subprocess.run(["udevadm", "verify", "--root=" + temp, "/" + path.name], capture_output=True, text=True, timeout=5)
                if "Unknown command" in result.stderr: self.skipTest("udevadm verify unavailable")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless(Path("/sys/devices").exists(), "Linux sysfs unavailable")
    def test_host_inventory_and_sample_details_read_only(self):
        inventory = Inventory()
        snapshot = inventory.snapshot()
        self.assertTrue(snapshot["devices"])
        ids = {d["id"] for d in snapshot["devices"]}
        self.assertTrue(all(not d["parent"] or d["parent"] in ids for d in snapshot["devices"]))
        samples = {}
        for device in snapshot["devices"]:
            samples.setdefault(device["category"], device)
            if device["subsystem"] == "hidraw": samples.setdefault("hidraw", device)
        for device in samples.values():
            with self.subTest(category=device["category"]):
                try: detail = inventory.detail(device["id"])
                except ValueError as error:
                    if str(error) == "device-disconnected": continue
                    raise
                self.assertEqual(detail["id"], device["id"])
                self.assertFalse(any("SERIAL" in key or key == "DEVLINKS" for key in detail["properties"]))
                for node in detail["nodes"]:
                    self.assertRegex(node["mode"], r"^0o[0-7]+$")
                    self.assertTrue(node["owner"])
        self.assertFalse(snapshot["capabilities"]["driverWrites"])
        self.assertFalse(snapshot["capabilities"]["privilegedRules"])

    def test_cli_json_no_host_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            env = {**os.environ, "XDG_STATE_HOME": temp}
            for payload, ok in (({"action": "preview", "rule": rule()}, True),
                                ({"action": "save", "rule": rule()}, True),
                                ({"action": "drafts"}, True),
                                ({"action": "install"}, False),
                                ({"action": "detail", "id": "/etc"}, False)):
                result = subprocess.run([sys.executable, str(BACKEND / "control.py"), "--request", json.dumps(payload)], capture_output=True, text=True, env=env, timeout=10)
                self.assertEqual(json.loads(result.stdout)["ok"], ok, result.stderr)
                self.assertEqual(result.returncode, 0 if ok else 1)
            self.assertFalse(list(Path(temp).rglob("*.rules")))

    def test_missing_udev_and_command_timeouts_degrade(self):
        import inventory
        with patch.object(inventory.subprocess, "run", side_effect=FileNotFoundError):
            self.assertEqual(inventory.command(["missing"]), ("", "tool-unavailable"))
        with patch.object(inventory.subprocess, "run", side_effect=subprocess.TimeoutExpired("fixture", 1)):
            self.assertEqual(inventory.command(["missing"]), ("", "command-timeout-or-denied"))
        with tempfile.TemporaryDirectory() as temp, patch.object(inventory, "command", return_value=("", "tool-unavailable")):
            self.assertEqual(Inventory(temp).snapshot()["warnings"], ["tool-unavailable"])


if __name__ == "__main__": unittest.main()
