"""UI projection of the exhaustive sysfs graph, without merging identical units.

Components are identifiable entities (CPU packages, bus functions, drives and
adapters), not a claim to count every chip on a board. Raw nodes stay separate.
"""
import re

CATEGORIES = [
    ("GPU", "Graphics", "memory"), ("CPU", "Processors", "developer_board"),
    ("Storage", "Storage", "storage"), ("Network", "Physical network", "lan"),
    ("Bluetooth", "Bluetooth adapters", "bluetooth"), ("USB", "USB & hubs", "usb"),
    ("Connected", "Connected devices / HID", "keyboard"), ("Audio", "Audio hardware", "volume_up"),
    ("Other", "Other components", "devices_other"), ("Virtual", "Virtual devices", "deployed_code")]


def project(devices):
    nodes = {d["id"]: d for d in devices}
    anchors, cpu_groups = {}, {}
    for d in devices:
        sub, kernel = d["subsystem"], d["kernel"]
        if sub == "cpu" and re.fullmatch(r"cpu\d+", kernel):
            cpu_groups.setdefault(d.get("packageId") or "unknown", []).append(d)
            continue
        physical_bus = sub == "pci" or sub == "usb" and d["kind"] == "device"
        drive = sub == "block" and d.get("devtype") == "disk"
        virtual = d["virtual"] and (sub == "net" or sub == "block" and drive or sub == "input" and bool(re.fullmatch(r"input\d+", kernel)) or sub in ("sound", "drm") and bool(re.fullmatch(r"card\d+", kernel)))
        if physical_bus or drive or virtual:
            anchors[d["id"]] = d
    # Fallback for non-PCI/non-USB platform endpoints. Keep only the highest
    # meaningful input/audio/network node, not its event/mouse children.
    for d in devices:
        if d["virtual"] or d["subsystem"] not in ("input", "sound", "net", "bluetooth", "hid"):
            continue
        current = d
        covered = False
        while current:
            if current["id"] in anchors:
                covered = True
                break
            current = nodes.get(current["parent"])
        if not covered:
            anchors[d["id"]] = d
    owners = {}
    for d in devices:
        current = d
        while current:
            if current["id"] in anchors:
                owners[d["id"]] = current["id"]
                break
            current = nodes.get(current["parent"])
    members = {identity: [] for identity in anchors}
    for identity, owner in owners.items(): members[owner].append(identity)
    entities = []
    for identity, d in anchors.items():
        group = [nodes[key] for key in members[identity]]
        subs = {n["subsystem"] for n in group}
        cat = "Other"
        if d["virtual"]: cat = "Virtual"
        elif d["subsystem"] == "block": cat = "Storage"
        elif d["category"] == "GPU" or "drm" in subs: cat = "GPU"
        elif "bluetooth" in subs: cat = "Bluetooth"
        elif "net" in subs or d["category"] == "Network": cat = "Network"
        elif "sound" in subs or d["category"] == "Audio": cat = "Audio"
        elif subs & {"hid", "hidraw", "input"}: cat = "Connected"
        elif d["subsystem"] == "usb": cat = "USB"
        interfaces = [n["id"] for n in group if n["kind"] == "interface"]
        parent = nodes.get(d["parent"])
        while parent and parent["id"] not in anchors: parent = nodes.get(parent["parent"])
        entities.append(dict(id=identity, name=d["name"], category=cat, bus=d["subsystem"],
            parent=parent["id"] if parent else "", memberIds=members[identity], interfaceIds=interfaces,
            interfaceCount=len(interfaces), vendor=d["vendor"], product=d["product"], driver=d["driver"],
            virtual=d["virtual"], hub=d.get("usbClass") == "09" or bool(re.fullmatch(r"usb\d+", d["kernel"])),
            summary=("USB hub" if d.get("usbClass") == "09" else d["subsystem"]) + " · " + d["kernel"]))
    for package, group in sorted(cpu_groups.items()):
        group.sort(key=lambda n: int(n["kernel"][3:]))
        representative = group[0]
        cores = {n.get("coreId") for n in group if n.get("coreId") not in (None, "")}
        identity = representative["id"]
        for n in group: owners[n["id"]] = identity
        entities.append(dict(id=identity, name="CPU" + (" · " + package if package != "unknown" else ""),
            category="CPU", bus="cpu", parent="", memberIds=[n["id"] for n in group], interfaceIds=[],
            interfaceCount=0, vendor="", product="", driver=representative["driver"], virtual=False, hub=False,
            logicalCpuCount=len(group), coreCount=len(cores) if cores else None,
            summary=f'{len(group)} logical CPUs' + (f' · {len(cores)} cores' if cores else '')))
    for d in devices:
        if d["id"] in owners: continue
        current = nodes.get(d["parent"])
        while current:
            if current["id"] in owners:
                owners[d["id"]] = owners[current["id"]]
                break
            current = nodes.get(current["parent"])
    order = {key: index for index, (key, _, _) in enumerate(CATEGORIES)}
    entities.sort(key=lambda e: (order[e["category"]], e["name"].casefold(), e["id"]))
    entity_map = {e["id"]: e for e in entities}
    for e in entities:
        trail, parent = [], e
        while parent:
            trail.insert(0, parent["name"])
            parent = entity_map.get(parent["parent"])
        e["breadcrumb"] = " › ".join(trail)
        # Search interface kernel names/drivers without exposing serial properties.
        e["searchText"] = " ".join([e["name"], e["id"], e["vendor"], e["product"], e["breadcrumb"],
            *[key + " " + nodes[key]["kernel"] + " " + nodes[key]["driver"] for key in e["memberIds"]]]).casefold()
    categories = [dict(id=key, name=name, icon=icon, count=sum(e["category"] == key for e in entities),
                       secondary=key in ("Other", "Virtual")) for key, name, icon in CATEGORIES]
    return dict(entities=entities, categories=categories, ownerByNode=owners,
                componentCount=sum(not e["virtual"] for e in entities), rawNodeCount=len(devices))
