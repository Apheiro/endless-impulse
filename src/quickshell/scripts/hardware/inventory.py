"""Read-only Linux hardware graph. No writes to sysfs, devfs or udev rules."""
import platform
import re
import shutil
import stat
import subprocess
from pathlib import Path
from projection import project

PRIVATE = re.compile(r"SERIAL|WWN|UUID|ADDRESS|UNIQ|ID_NET_NAME_MAC|DEVLINKS|(?:^|_)PHYS$", re.I)


def read(path, limit=8192):
    try:
        with path.open(errors="replace") as stream:
            return stream.read(limit).strip()
    except OSError:
        return ""


def command(args, timeout=8):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
        return result.stdout if result.returncode == 0 else "", "" if result.returncode == 0 else "command-failed"
    except FileNotFoundError:
        return "", "tool-unavailable"
    except (OSError, subprocess.TimeoutExpired):
        return "", "command-timeout-or-denied"


def parse_udev(text):
    records = {}
    for block in text.split("\n\n"):
        path, props = "", {}
        for line in block.splitlines():
            if line.startswith("P: "):
                path = line[3:]
            elif line.startswith("E: ") and "=" in line:
                key, value = line[3:].split("=", 1)
                props[key] = value
        if path.startswith("/devices/"):
            records[path] = props
    return records


def public_properties(props):
    # Device serials, filesystem IDs and network addresses are never exported.
    return {k: v for k, v in props.items() if not PRIVATE.search(k)}


def category(subsystem, path, props):
    if subsystem == "cpu": return "CPU"
    if subsystem in ("block", "nvme", "scsi", "ata_port", "ata_link", "ata_device"): return "Storage"
    if subsystem == "drm": return "GPU"
    if subsystem == "sound": return "Audio"
    if subsystem == "net": return "Network"
    if subsystem == "bluetooth": return "Bluetooth"
    if subsystem in ("hid", "hidraw", "input"): return "HID / Input"
    if subsystem == "usb": return "USB"
    if subsystem == "pci":
        try: cls = int(props.get("PCI_CLASS", "0"), 16)
        except ValueError: cls = 0
        if cls >> 16 == 3: return "GPU"
        if cls >> 16 == 2: return "Network"
        if cls >> 8 in (0x0401, 0x0403): return "Audio"
        return "PCI"
    if "/virtual/" in path: return "Virtual"
    return "Platform / Other"


class Inventory:
    def __init__(self, sys_root="/sys", dev_root="/dev", use_tools=True):
        self.sys = Path(sys_root).resolve()
        self.dev = Path(dev_root).resolve()
        self.use_tools = use_tools

    def path(self, identity):
        if not isinstance(identity, str) or not identity.startswith("/devices/") or ".." in identity.split("/"):
            raise ValueError("invalid-device-path")
        path = (self.sys / identity.lstrip("/")).resolve()
        if not path.is_relative_to(self.sys / "devices") or not path.is_dir():
            raise ValueError("device-disconnected")
        return path

    def snapshot(self):
        raw, error = command(["udevadm", "info", "--export-db"]) if self.use_tools else ("", "tools-disabled")
        records = parse_udev(raw)
        paths = set(records)
        # Bus and class symlinks cover physical devices and interfaces, including CPUs
        # without uevents. Do not recursively walk disk or firmware contents.
        for base in (self.sys / "bus", self.sys / "class"):
            if not base.is_dir(): continue
            for group in base.iterdir():
                folder = group / "devices" if base.name == "bus" else group
                try:
                    for entry in folder.iterdir():
                        target = entry.resolve()
                        if target.is_dir() and target.is_relative_to(self.sys / "devices"):
                            paths.add("/" + str(target.relative_to(self.sys)))
                except OSError:
                    continue
        # Preserve intervening controllers/hubs in the physical ancestry.
        for identity in list(paths):
            parent = Path(identity).parent
            while str(parent) != "/devices" and str(parent).startswith("/devices/"):
                paths.add(str(parent))
                parent = parent.parent
        devices = {}
        for identity in sorted(paths):
            try: path = self.path(identity)
            except ValueError: continue
            props = records.get(identity, {})
            subsystem = (path / "subsystem").resolve().name if (path / "subsystem").exists() else props.get("SUBSYSTEM", "")
            props = {**dict(line.split("=", 1) for line in read(path / "uevent").splitlines() if "=" in line), **props}
            driver = (path / "driver").resolve().name if (path / "driver").exists() else ""
            vendor = read(path / "idVendor") or read(path / "vendor") or props.get("ID_VENDOR_ID", "")
            product = read(path / "idProduct") or read(path / "device") or props.get("ID_MODEL_ID", "")
            name = read(path / "product") or props.get("ID_MODEL_FROM_DATABASE") or props.get("ID_MODEL") or read(path / "name") or path.name
            kind = "interface" if subsystem in ("hid", "hidraw", "input", "net", "sound", "drm", "tty", "bluetooth") or (subsystem == "usb" and ":" in path.name) else "device"
            if not subsystem: kind = "container"
            devices[identity] = dict(id=identity, parent="", name=name, kernel=path.name, subsystem=subsystem,
                category=category(subsystem, identity, props), vendor=vendor, product=product, driver=driver,
                kind=kind, virtual="/virtual/" in identity, devtype=props.get("DEVTYPE", ""),
                packageId=read(path / "topology/physical_package_id") if subsystem == "cpu" else "",
                coreId=read(path / "topology/core_id") if subsystem == "cpu" else "",
                usbClass=read(path / "bDeviceClass") if subsystem == "usb" else "")
        for identity, device in devices.items():
            parent = str(Path(identity).parent)
            device["parent"] = parent if parent in devices else ""
            physical = device
            ancestor = device
            # Skip structural directories and logical interfaces. The nearest
            # USB device or PCI function is the physical component, even when
            # sysfs inserts hidraw/input/sound directories between the nodes.
            while ancestor:
                if ancestor["subsystem"] in ("usb", "pci", "cpu", "nvme") and ancestor["kind"] == "device":
                    physical = ancestor
                    break
                ancestor = devices.get(ancestor["parent"])
            device["physicalId"] = physical["id"]
        return dict(projection=project(list(devices.values())), kernel=dict(release=platform.release(), architecture=platform.machine()), devices=list(devices.values()), warnings=[error] if error else [],
                    tools={tool: bool(shutil.which(tool)) for tool in ("udevadm", "getfacl", "lsusb", "lsblk")},
                    capabilities={"inventory": True, "driverWrites": False, "privilegedRules": False})

    def detail(self, identity):
        path = self.path(identity)
        raw, error = command(["udevadm", "info", "--query=property", "--path", str(path)]) if self.use_tools else ("", "tools-disabled")
        props = dict(line.split("=", 1) for line in raw.splitlines() if "=" in line)
        driver_path = (path / "driver").resolve() if (path / "driver").exists() else None
        module = (driver_path / "module").resolve() if driver_path and (driver_path / "module").exists() else None
        parameters = {}
        if module and (module / "parameters").is_dir():
            for item in (module / "parameters").iterdir():
                if not PRIVATE.search(item.name):
                    parameters[item.name] = read(item) or "unavailable-or-empty"
        attrs = {}
        for key in ("idVendor", "idProduct", "vendor", "device", "class", "bcdUSB", "bcdDevice", "bNumInterfaces", "bNumEndpoints", "maxchild", "speed", "duplex", "operstate", "carrier", "bDeviceClass", "bInterfaceClass", "bInterfaceNumber", "revision", "version", "firmware_node/path", "power/control", "power/runtime_status", "power/runtime_active_time", "power/runtime_suspended_time", "authorized", "removable", "size", "queue/logical_block_size", "model", "manufacturer", "online", "topology/core_id", "topology/physical_package_id", "capabilities/ev", "capabilities/key", "capabilities/rel", "capabilities/abs", "capabilities/sw", "modalias"):
            value = read(path / key)
            units = {"size": "size (512-byte sectors)", "queue/logical_block_size": "logical block size (bytes)",
                     "speed": "speed (Mbit/s)", "power/runtime_active_time": "runtime active time (ms)",
                     "power/runtime_suspended_time": "runtime suspended time (ms)"}
            if value: attrs[units.get(key, key)] = value
        firmware = {}
        for key in ("firmware_rev", "fwrev", "firmware_version"):
            value = read(path / key)
            if value: firmware[key] = value
        nodes = []
        # Only udev-provided node, validated beneath dev_root; never follow arbitrary paths.
        node_name = props.get("DEVNAME", "")
        if node_name.startswith("/dev/"):
            node = self.dev / node_name[5:]
            try:
                resolved = node.resolve()
                if resolved.is_relative_to(self.dev):
                    info = node.stat()
                    if stat.S_ISCHR(info.st_mode) or stat.S_ISBLK(info.st_mode):
                        acl, acl_error = command(["getfacl", "--omit-header", "--absolute-names", "--", str(node)]) if self.use_tools else ("", "tools-disabled")
                        import pwd, grp
                        try: owner = pwd.getpwuid(info.st_uid).pw_name
                        except KeyError: owner = str(info.st_uid)
                        try: group = grp.getgrgid(info.st_gid).gr_name
                        except KeyError: group = str(info.st_gid)
                        nodes.append(dict(path=str(node), mode=oct(stat.S_IMODE(info.st_mode)), owner=owner, group=group, acl=acl, aclError=acl_error))
            except OSError:
                error = error or "node-unavailable"
        # Rule selector uses one USB ancestor carrying both IDs (udev ATTRS semantics).
        usb = None
        for ancestor in (path, *path.parents):
            if not ancestor.is_relative_to(self.sys / "devices"): break
            vendor, product = read(ancestor / "idVendor"), read(ancestor / "idProduct")
            if re.fullmatch(r"[0-9a-fA-F]{4}", vendor) and re.fullmatch(r"[0-9a-fA-F]{4}", product):
                usb = dict(vendor=vendor.lower(), product=product.lower(), path="/" + str(ancestor.relative_to(self.sys)))
                break
        subsystem = (path / "subsystem").resolve().name if (path / "subsystem").exists() else props.get("SUBSYSTEM", "")
        supported_kernel = {
            "hidraw": r"hidraw[0-9]+", "input": r"event[0-9]+",
            "tty": r"tty(?:USB|ACM)[0-9]+", "usb": r"[0-9]+-[0-9]+(?:\.[0-9]+)*"
        }
        rule_supported = bool(usb and subsystem in supported_kernel and re.fullmatch(supported_kernel[subsystem], path.name))
        return dict(id=identity, sysfs=str(path), kernel=path.name, subsystem=subsystem, ruleSupported=rule_supported,
            parent=str(Path(identity).parent), driver=driver_path.name if driver_path else "",
            driverPath=str(driver_path) if driver_path else "", module=module.name if module else "",
            moduleState=read(module / "initstate") if module else "", parameters=parameters,
            binding="bound" if driver_path else "unbound-or-not-applicable", attributes=attrs,
            firmware=firmware, properties=public_properties(props), nodes=nodes, usbSelector=usb,
            diagnostics=[error] if error else [],
            limitations=["kernel-log-not-read", "driver-controls-read-only", "serials-hidden"])
