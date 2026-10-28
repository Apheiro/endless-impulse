#!/usr/bin/env python3
"""Typed Hyprland settings with isolated persistence and a detached rollback guard."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import fcntl
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time

CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
STATE = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "artificial-impulse/desktop"
DIRECTORY = CONFIG / "artificial-impulse"
SAVED = DIRECTORY / "hyprland.json"
LUA = DIRECTORY / "hyprland.lua"
PENDING = STATE / "pending.json"
MAIN = CONFIG / "hypr/hyprland.lua"
HOOK = 'require("hyprland.services.desktop").load()'
TIMEOUT = 20


def field(key, label, section, kind, default, minimum=None, maximum=None, choices=None):
    return dict(key=key, label=label, section=section, type=kind, default=default,
                minimum=minimum, maximum=maximum, choices=choices or [])


FIELDS = [
    field("general:layout", "Tiling layout", "Layout", "enum", "dwindle", choices=["dwindle", "master", "scrolling"]),
    field("general:gaps_in", "Inner gaps (1–4 values)", "Layout", "gap", "4"),
    field("general:gaps_out", "Outer gaps (1–4 values)", "Layout", "gap", "5"),
    field("general:gaps_workspaces", "Space between workspaces", "Layout", "int", 50, 0, 300),
    field("dwindle:preserve_split", "Preserve split direction", "Layout", "bool", True),
    field("dwindle:smart_split", "Choose split direction from pointer", "Layout", "bool", False),
    field("misc:focus_on_activate", "Focus windows requesting activation", "Layout", "bool", True),
    field("general:border_size", "Border width", "Borders", "int", 1, 0, 20),
    field("general:col:active_border", "Focused border colors", "Borders", "gradient", "rgba(0DB7D455)"),
    field("general:col:inactive_border", "Inactive border colors", "Borders", "gradient", "rgba(31313600)"),
    field("general:resize_on_border", "Resize by dragging borders", "Borders", "bool", True),
    field("decoration:rounding", "Corner radius", "Borders", "int", 18, 0, 100),
    field("decoration:rounding_power", "Corner shape", "Borders", "float", 2.5, 1, 10),
    field("decoration:active_opacity", "Focused window opacity", "Opacity", "float", 1, 0.1, 1),
    field("decoration:inactive_opacity", "Inactive window opacity", "Opacity", "float", 1, 0.1, 1),
    field("decoration:dim_inactive", "Dim inactive windows", "Opacity", "bool", True),
    field("decoration:dim_strength", "Dimming strength", "Opacity", "float", 0.05, 0, 1),
    field("decoration:blur:enabled", "Enable blur", "Blur", "bool", True),
    field("decoration:blur:size", "Blur radius", "Blur", "int", 10, 1, 40),
    field("decoration:blur:passes", "Blur passes", "Blur", "int", 3, 1, 8),
    field("decoration:shadow:enabled", "Enable shadows", "Shadows", "bool", True),
    field("decoration:shadow:range", "Shadow range", "Shadows", "int", 20, 0, 100),
    field("animations:enabled", "Enable window and workspace animations", "Animations", "bool", True),
    field("input:kb_layout", "Keyboard layout", "Keyboard", "text", "us"),
    field("input:kb_variant", "Keyboard variant", "Keyboard", "text", ""),
    field("input:kb_options", "Keyboard options", "Keyboard", "text", ""),
    field("input:repeat_delay", "Key repeat delay (ms)", "Keyboard", "int", 250, 100, 2000),
    field("input:repeat_rate", "Key repeat rate", "Keyboard", "int", 35, 1, 100),
    field("input:numlock_by_default", "Enable Num Lock by default", "Keyboard", "bool", True),
    field("input:sensitivity", "Pointer sensitivity", "Pointer", "float", 0, -1, 1),
    field("input:accel_profile", "Pointer acceleration", "Pointer", "enum", "", choices=["", "flat", "adaptive"]),
    field("input:left_handed", "Left-handed buttons", "Pointer", "bool", False),
    field("input:natural_scroll", "Natural scrolling (mouse)", "Pointer", "bool", False),
    field("input:follow_mouse", "Focus follows pointer", "Pointer", "int", 1, 0, 3),
    field("input:touchpad:natural_scroll", "Natural scrolling", "Touchpad", "bool", True),
    field("input:touchpad:disable_while_typing", "Disable touchpad while typing", "Touchpad", "bool", True),
    field("input:touchpad:tap_to_click", "Tap to click", "Touchpad", "bool", True),
    field("input:touchpad:clickfinger_behavior", "Click with multiple fingers", "Touchpad", "bool", True),
    field("input:touchpad:scroll_factor", "Touchpad scroll speed", "Touchpad", "float", 0.7, 0.1, 5),
]
BY_KEY = {entry["key"]: entry for entry in FIELDS}
DEVICE_KEYS = {
    "mice": {"sensitivity": "input:sensitivity", "accel_profile": "input:accel_profile",
             "left_handed": "input:left_handed", "natural_scroll": "input:natural_scroll"},
    "keyboards": {name: "input:" + name for name in
                  ("kb_layout", "kb_variant", "kb_options", "repeat_delay", "repeat_rate", "numlock_by_default")},
}


def empty():
    return dict(version=1, options={}, monitors={}, devices={})


def read_json(path, fallback=None):
    return json.loads(path.read_text()) if path.exists() else fallback


def atomic(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as target:
        temporary = Path(target.name)
        try:
            target.write(content)
            target.flush()
            os.fsync(target.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    temporary.chmod(0o600)
    temporary.replace(path)


def write_json(path, data):
    atomic(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


@contextmanager
def locked():
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / "lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def ipc(*arguments, as_json=False):
    result = subprocess.run(["hyprctl", *arguments, *(["-j"] if as_json else [])],
                            capture_output=True, text=True, timeout=8)
    if result.returncode:
        raise ValueError(result.stderr.strip() or result.stdout.strip() or "Hyprland did not respond")
    return json.loads(result.stdout) if as_json else result.stdout.strip()


def saved():
    data = read_json(SAVED, empty())
    if data.get("version") != 1 or any(not isinstance(data.get(key), dict) for key in ("options", "monitors", "devices")):
        raise ValueError("Unsupported managed settings file")
    return data


def option_value(entry):
    try:
        result = ipc("getoption", entry["key"], as_json=True)
        if "gradient" in result:
            colors = result["gradient"].split()
            value = " ".join("rgba(" + color[2:] + color[:2] + ")" if re.fullmatch(r"[0-9a-fA-F]{8}", color) else color for color in colors)
            return entry["key"], value, True
        for kind in ("bool", "int", "float", "str", "css"):
            if kind in result:
                value = result[kind]
                if kind == "str" and value == "[[EMPTY]]":
                    value = ""
                return entry["key"], bool(value) if entry["type"] == "bool" else value, True
    except (ValueError, subprocess.SubprocessError):
        pass
    return entry["key"], entry["default"], False


def monitor_spec(monitor):
    return dict(mode=f'{monitor["width"]}x{monitor["height"]}@{monitor["refreshRate"]:.2f}Hz',
                x=monitor.get("x", 0), y=monitor.get("y", 0), scale=monitor.get("scale", 1),
                transform=monitor.get("transform", 0))


def transaction():
    pending = read_json(PENDING)
    if not pending:
        return None
    return dict(token=pending["token"], deadline=pending["deadline"])


def integrated():
    module = CONFIG / "hypr/hyprland/services/desktop.lua"
    return MAIN.is_file() and HOOK in MAIN.read_text() and module.is_file()


def snapshot():
    monitors = ipc("monitors", "all", as_json=True)
    devices = ipc("devices", as_json=True)
    with ThreadPoolExecutor(max_workers=6) as pool:
        options = list(pool.map(option_value, FIELDS))
    for monitor in monitors:
        monitor["current"] = monitor_spec(monitor)
    device_list = [dict(name=device["name"], kind=kind, details=device)
                   for kind in DEVICE_KEYS for device in devices.get(kind, [])]
    return dict(monitors=monitors, devices=device_list, fields=FIELDS,
                values={key: value for key, value, supported in options},
                supported={key: supported for key, value, supported in options},
                saved=saved(), integrated=integrated(), transaction=transaction())


def validate_value(entry, value):
    kind = entry["type"]
    if kind == "bool":
        if type(value) is not bool:
            raise ValueError(entry["label"] + ": expected a switch value")
    elif kind in ("int", "float"):
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(entry["label"] + ": expected a finite number")
        if kind == "int" and int(value) != value:
            raise ValueError(entry["label"] + ": expected a whole number")
        if not entry["minimum"] <= value <= entry["maximum"]:
            raise ValueError(f'{entry["label"]}: must be between {entry["minimum"]} and {entry["maximum"]}')
    elif kind == "enum":
        if value not in entry["choices"]:
            raise ValueError(entry["label"] + ": unsupported choice")
    elif kind == "text":
        if not isinstance(value, str) or len(value) > 256 or not re.fullmatch(r"[A-Za-z0-9_,:+.\-]*", value):
            raise ValueError(entry["label"] + ": invalid keyboard identifier")
        if entry["key"].endswith("kb_layout") and not value:
            raise ValueError("Keyboard layout cannot be empty")
    elif kind == "gradient":
        if not isinstance(value, str) or len(value) > 512 or not re.fullmatch(r"(?:rgba\([0-9a-fA-F]{8}\)|rgb\([0-9a-fA-F]{6}\))(?:\s+(?:rgba\([0-9a-fA-F]{8}\)|rgb\([0-9a-fA-F]{6}\))){0,9}(?:\s+\d{1,3}deg)?", value.strip()):
            raise ValueError(entry["label"] + ": use rgb(RRGGBB) or rgba(RRGGBBAA), optionally followed by another color and an angle")
        angle = re.search(r"(\d+)deg$", value.strip())
        if angle and int(angle[1]) > 360:
            raise ValueError("Gradient angle must be between 0 and 360 degrees")
    elif kind == "gap":
        if not isinstance(value, str) or not re.fullmatch(r"\d+(?:\s+\d+){0,3}", value.strip()):
            raise ValueError(entry["label"] + ": enter one to four pixel values")
        if any(int(part) > 300 for part in value.split()):
            raise ValueError("Gaps must be between 0 and 300")
    return value


def parse_mode(mode):
    match = re.fullmatch(r"(\d{2,5})x(\d{2,5})@([\d.]+)(?:Hz)?", mode or "")
    if not match:
        raise ValueError("Choose an advertised resolution and refresh rate")
    width, height, refresh = int(match[1]), int(match[2]), float(match[3])
    if not math.isfinite(refresh) or not 1 <= refresh <= 1000:
        raise ValueError("Invalid refresh rate")
    return width, height, refresh


def validate_monitor(value, current):
    if not isinstance(value, dict) or set(value) != {"mode", "x", "y", "scale", "transform"}:
        raise ValueError("Incomplete monitor configuration")
    width, height, refresh = parse_mode(value["mode"])
    modes = current.get("availableModes", []) + [current["current"]["mode"]]
    if not any((w == width and h == height and abs(hz - refresh) < 0.02) for w, h, hz in map(parse_mode, modes)):
        raise ValueError("The selected mode is not advertised by this monitor")
    for coordinate in ("x", "y"):
        if type(value[coordinate]) is not int or abs(value[coordinate]) > 1000000:
            raise ValueError("Monitor coordinates must be whole pixels within ±1,000,000")
    scale = value["scale"]
    if type(scale) not in (int, float) or not math.isfinite(scale) or not 0.5 <= scale <= 4:
        raise ValueError("Monitor scale must be between 50% and 400%")
    if any(abs(dimension / scale - round(dimension / scale)) > 0.01 for dimension in (width, height)):
        raise ValueError("This scale does not divide the resolution into whole logical pixels")
    if type(value["transform"]) is not int or value["transform"] not in range(8):
        raise ValueError("Unknown monitor orientation")
    return value


def merge_patch(previous, patch, live):
    if not isinstance(patch, dict) or set(patch) - {"options", "monitors", "devices"}:
        raise ValueError("Unsupported settings payload")
    result = json.loads(json.dumps(previous))
    for section in ("options", "monitors", "devices"):
        updates = patch.get(section, {})
        if not isinstance(updates, dict):
            raise ValueError("Invalid " + section + " payload")
        for key, value in updates.items():
            if value is None:
                if key not in result[section]:
                    continue
                del result[section][key]
                continue
            if section == "options":
                if key not in BY_KEY or not live["supported"].get(key):
                    raise ValueError("Unsupported Hyprland option: " + key)
                value = validate_value(BY_KEY[key], value)
            elif section == "monitors":
                monitor = next((m for m in live["monitors"] if m["name"] == key and not m.get("disabled")), None)
                if monitor is None:
                    raise ValueError("Monitor is disconnected or disabled: " + key)
                value = validate_monitor(value, monitor)
            else:
                device = next((d for d in live["devices"] if d["name"] == key), None)
                if device is None or not isinstance(value, dict):
                    raise ValueError("Unknown input device: " + key)
                allowed = DEVICE_KEYS[device["kind"]]
                if set(value) - set(allowed):
                    raise ValueError("Unsupported per-device option")
                value = {name: validate_value(BY_KEY[allowed[name]], setting) for name, setting in value.items()}
            result[section][key] = value
    return result


def lua_value(value):
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) in (float, int):
        if not math.isfinite(value):
            raise ValueError("Non-finite Lua number")
        return str(value)
    if isinstance(value, str):
        if any(ord(character) < 32 for character in value):
            raise ValueError("Control characters are not allowed")
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, dict):
        return "{" + ",".join("[" + lua_value(key) + "]=" + lua_value(item) for key, item in sorted(value.items())) + "}"
    raise ValueError("Unsupported Lua value")


def generate(data):
    nested = {}
    for key, value in sorted(data["options"].items()):
        if key not in BY_KEY:
            raise ValueError("Unrecognized managed option")
        validate_value(BY_KEY[key], value)
        parts = key.replace("tap-to-click", "tap_to_click").split(":")
        node = nested
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    lines = ["-- Artificial Impulse: generated desktop overrides. Edit through Settings.\n"]
    if nested:
        lines.append("hl.config(" + lua_value(nested) + ")\n")
    for name, value in sorted(data["monitors"].items()):
        spec = dict(output=name, mode=value["mode"], position=f'{value["x"]}x{value["y"]}',
                    scale=value["scale"], transform=value["transform"])
        lines.append("hl.monitor(" + lua_value(spec) + ")\n")
    for name, value in sorted(data["devices"].items()):
        lines.append("hl.device(" + lua_value(dict(value, name=name)) + ")\n")
    return "".join(lines)


def check_reload():
    ipc("reload")
    errors = ipc("configerrors")
    if errors and errors != "ok":
        raise ValueError(errors)


def rollback(pending):
    previous = pending["previousLua"]
    if previous is None:
        LUA.unlink(missing_ok=True)
    else:
        atomic(LUA, previous)
    ipc("reload")
    # Restore actual monitor geometry even if it was originally set by another UI at runtime.
    connected = {m["name"] for m in ipc("monitors", "all", as_json=True) if not m.get("disabled")}
    baseline = empty()
    baseline["monitors"] = {name: value for name, value in pending["baselineMonitors"].items() if name in connected}
    baseline["options"] = pending["baselineOptions"]
    if baseline["options"] or baseline["monitors"]:
        ipc("eval", generate(baseline))
    PENDING.unlink(missing_ok=True)
    (STATE / "preview-session").unlink(missing_ok=True)


def recover_expired():
    pending = read_json(PENDING)
    if pending and (time.time() >= pending["deadline"] or pending.get("session") != os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "")):
        rollback(pending)
    elif not pending:
        (STATE / "preview-session").unlink(missing_ok=True)


def preview(patch):
    if not integrated():
        raise ValueError("Enable the Artificial Impulse desktop integration first")
    if PENDING.exists():
        raise ValueError("Confirm or revert the current preview first")
    if ipc("configerrors") not in ("", "ok"):
        raise ValueError("Resolve existing Hyprland configuration errors before testing changes")
    live = snapshot()
    candidate = merge_patch(saved(), patch, live)
    changed_keys = set(saved()["options"]) | set(candidate["options"])
    pending = dict(token=secrets.token_hex(16), deadline=time.time() + TIMEOUT,
                   session=os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", ""), candidate=candidate,
                   previousLua=LUA.read_text() if LUA.exists() else None,
                   baselineMonitors={m["name"]: m["current"] for m in live["monitors"] if not m.get("disabled")},
                   baselineOptions={key: live["values"][key] for key in changed_keys})
    source = generate(candidate)
    atomic(STATE / "last-good.lua", pending["previousLua"] or "-- No confirmed Artificial Impulse desktop overrides.\n")
    write_json(PENDING, pending)
    try:
        atomic(STATE / "preview-session", pending["session"] + "\n" + str(pending["deadline"]) + "\n")
        with (STATE / "rollback.log").open("a") as log:
            subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "watch", pending["token"]],
                             stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
        atomic(LUA, source)
        check_reload()
    except Exception:
        rollback(pending)
        raise
    return dict(transaction=transaction())


def confirm(token):
    pending = read_json(PENDING)
    if not pending or pending["token"] != token:
        raise ValueError("This preview is no longer active")
    if time.time() >= pending["deadline"]:
        rollback(pending)
        raise ValueError("Preview expired; previous settings restored")
    if ipc("configerrors") not in ("", "ok"):
        rollback(pending)
        raise ValueError("Hyprland reported configuration errors; changes reverted")
    write_json(SAVED, pending["candidate"])
    PENDING.unlink()
    (STATE / "preview-session").unlink(missing_ok=True)
    return dict(transaction=None)


def watch(token):
    failures = 0
    while True:
        try:
            with locked():
                pending = read_json(PENDING)
                if not pending or pending["token"] != token:
                    return
                remaining = pending["deadline"] - time.time()
                if remaining <= 0:
                    rollback(pending)
                    return
            time.sleep(min(remaining, 1))
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            failures += 1
            print("Rollback retry:", error, flush=True)
            if failures >= 6:
                raise
            time.sleep(min(2 ** failures, 10))


def install():
    if not MAIN.is_file():
        raise ValueError("No Hyprland Lua entry point found at " + str(MAIN))
    if PENDING.exists():
        raise ValueError("Finish the current preview first")
    if integrated():
        return dict(integrated=True)
    source = Path(__file__).resolve().parents[4] / "hypr/hyprland/services/desktop.lua"
    if not source.is_file():
        raise ValueError("Desktop integration module is missing")
    destination = CONFIG / "hypr/hyprland/services/desktop.lua"
    before = MAIN.read_text()
    previous_module = destination.read_text() if destination.exists() else None
    backup = STATE / "backups" / (time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(4))
    backup.mkdir(parents=True)
    shutil.copy2(MAIN, backup / "hyprland.lua")
    if destination.exists():
        shutil.copy2(destination, backup / "desktop.lua")
    try:
        atomic(destination, source.read_text())
        if HOOK not in before:
            atomic(MAIN, before.rstrip() + "\n\n-- Artificial Impulse desktop settings\n" + HOOK + "\n")
        check_reload()
    except Exception:
        atomic(MAIN, before)
        if previous_module is None:
            destination.unlink(missing_ok=True)
        else:
            atomic(destination, previous_module)
        ipc("reload")
        raise
    return dict(integrated=True, backup=str(backup))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["snapshot", "preview", "confirm", "revert", "transaction", "watch", "install", "recover"])
    parser.add_argument("token", nargs="?")
    arguments = parser.parse_args()
    if arguments.action == "watch":
        watch(arguments.token)
        return
    with locked():
        recover_expired()
        if arguments.action == "snapshot":
            result = snapshot()
        elif arguments.action == "preview":
            result = preview(json.load(sys.stdin))
        elif arguments.action == "confirm":
            result = confirm(arguments.token)
        elif arguments.action in ("revert", "recover"):
            pending = read_json(PENDING)
            if arguments.action == "revert" and (not pending or pending["token"] != arguments.token):
                raise ValueError("This preview is no longer active")
            if pending:
                rollback(pending)
            result = dict(transaction=None)
        elif arguments.action == "install":
            result = install()
        else:
            result = dict(transaction=transaction())
    print(json.dumps(dict(ok=True, **result), ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(json.dumps(dict(ok=False, error=str(error)), ensure_ascii=False))
        sys.exit(1)
