"""Physical UI model acceptance fixtures. No host writes or fabricated production data."""
from pathlib import Path
import sys
import tempfile
import unittest

BACKEND = Path(__file__).resolve().parents[1] / "src/quickshell/scripts/hardware"
sys.path.insert(0, str(BACKEND))
from inventory import Inventory, category
from projection import project


class HardwareProjectionTests(unittest.TestCase):
    def fixture(self, root):
        def add(identity, subsystem, attrs=None, uevent=""):
            path = root / identity.lstrip("/")
            path.mkdir(parents=True, exist_ok=True)
            bus = root / "bus" / subsystem
            (bus / "devices").mkdir(parents=True, exist_ok=True)
            (path / "subsystem").symlink_to(bus)
            # Class names need not be globally unique; use distinct fake symlink keys.
            key = identity.replace("/", "_")
            (bus / "devices" / key).symlink_to(path)
            (path / "uevent").write_text(uevent)
            for key, value in (attrs or {}).items():
                target = path / key
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(value)
        for number in range(4):
            add(f"/devices/system/cpu/cpu{number}", "cpu", {"topology/physical_package_id": "0", "topology/core_id": str(number // 2)})
        controller = "/devices/pci0000:00/0000:00:01.0"
        add(controller, "pci", uevent="PCI_CLASS=0c0330")
        hub = controller + "/usb1/1-1"
        add(hub, "usb", {"idVendor": "aaaa", "idProduct": "0001", "bDeviceClass": "09", "product": "Fixture hub"})
        for port in ("1-1.1", "1-1.2"):
            keyboard = hub + "/" + port
            add(keyboard, "usb", {"idVendor": "abcd", "idProduct": "0123", "product": "Identical keyboard"})
            for number in range(3):
                interface = keyboard + f"/{port}:1.{number}"
                add(interface, "usb")
                add(interface + f"/hidraw/hidraw{number}", "hidraw")
        gpu = "/devices/pci0000:00/0000:00:02.0"
        add(gpu, "pci", {"vendor": "0xaaaa", "device": "0x1234"}, "PCI_CLASS=030000")
        add(gpu + "/drm/card0", "drm")
        add(gpu + "/drm/card0/card0-DP-1", "drm")
        bluetooth = hub + "/1-1.3"
        add(bluetooth, "usb", {"idVendor": "bbbb", "idProduct": "0012", "product": "Bluetooth adapter"})
        add(bluetooth + "/1-1.3:1.0", "usb")
        add(bluetooth + "/1-1.3:1.0/bluetooth/hci0", "bluetooth")
        add("/devices/virtual/net/lo", "net")
        add(controller + "/ata1/host0/target0/disk0/block/sda", "block", uevent="DEVTYPE=disk")
        return Inventory(root, use_tools=False).snapshot()

    def test_physical_entities_interfaces_cpu_gpu_bluetooth_and_hubs(self):
        with tempfile.TemporaryDirectory() as temp:
            snapshot = self.fixture(Path(temp))
        p = snapshot["projection"]
        by_id = {e["id"]: e for e in p["entities"]}
        cpus = [e for e in p["entities"] if e["category"] == "CPU"]
        self.assertEqual(len(cpus), 1)
        self.assertEqual(cpus[0]["logicalCpuCount"], 4)
        self.assertEqual(cpus[0]["coreCount"], 2)
        keyboards = [e for e in p["entities"] if e["name"] == "Identical keyboard"]
        self.assertEqual(len(keyboards), 2, "Identical vendor/product must not merge physical units")
        for keyboard in keyboards:
            self.assertEqual(len([key for key in keyboard["interfaceIds"] if "/hidraw/hidraw" in key]), 3)
            self.assertTrue(by_id[keyboard["parent"]]["hub"])
            self.assertIn("Fixture hub", keyboard["breadcrumb"])
            for key in keyboard["interfaceIds"]:
                self.assertEqual(p["ownerByNode"][key], keyboard["id"])
                self.assertIn(key, keyboard["searchText"])
        gpu = next(e for e in p["entities"] if e["category"] == "GPU")
        self.assertEqual(len(gpu["interfaceIds"]), 2)
        self.assertEqual(sum(e["category"] == "Bluetooth" for e in p["entities"]), 1)
        self.assertEqual(sum(e["category"] == "Storage" for e in p["entities"]), 1)
        self.assertEqual(sum(e["category"] == "Virtual" for e in p["entities"]), 1)
        self.assertTrue(next(c for c in p["categories"] if c["id"] == "Virtual")["secondary"])
        self.assertGreater(p["rawNodeCount"], p["componentCount"])
        self.assertEqual(sum(c["count"] for c in p["categories"]), len(p["entities"]))
        self.assertEqual([e["id"] for e in project(snapshot["devices"])["entities"]], list(by_id))

    def test_large_technical_universe_does_not_become_components(self):
        devices = [dict(id=f"/devices/platform/technical/{i}", parent="", name=str(i), kernel=str(i), subsystem="", category="Platform / Other", kind="container", virtual=False, vendor="", product="", driver="") for i in range(1500)]
        projection = project(devices)
        self.assertEqual(projection["rawNodeCount"], 1500)
        self.assertEqual(projection["componentCount"], 0)
        self.assertEqual(projection["entities"], [])

    def test_pci_class_with_or_without_leading_zero(self):
        for cls in ("30000", "030000"):
            self.assertEqual(category("pci", "", {"PCI_CLASS": cls}), "GPU")
        self.assertEqual(category("pci", "", {"PCI_CLASS": "020000"}), "Network")
        self.assertEqual(category("pci", "", {"PCI_CLASS": "040300"}), "Audio")


if __name__ == "__main__": unittest.main()
