#!/usr/bin/env python3
"""Dock minimization through an isolated special workspace, with session-scoped origins."""
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

WORKSPACE = "special:artificial-minimized"
STATE = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "artificial-impulse/minimized.json"


def ipc(*arguments, json_result=False):
    result = subprocess.run(["hyprctl", *arguments, *(["-j"] if json_result else [])], capture_output=True, text=True, timeout=5)
    if result.returncode:
        raise ValueError(result.stderr.strip() or result.stdout.strip() or "Hyprland did not respond")
    return json.loads(result.stdout) if json_result else result.stdout


def quote(value):
    return '"' + ''.join('\\' + format(ord(c), '03d') if ord(c) < 32 else '\\' + c if c in '\\"' else c for c in str(value)) + '"'


def dispatch(code):
    return ipc("eval", "hl.dispatch(" + code + ")")


def write(entries):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=STATE.parent, delete=False) as target:
        path = Path(target.name)
        try:
            json.dump(dict(session=os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", ""), windows=entries), target)
            target.flush()
            os.fsync(target.fileno())
        except BaseException:
            path.unlink(missing_ok=True)
            raise
    path.replace(STATE)


def load(clients):
    data = json.loads(STATE.read_text()) if STATE.exists() else {}
    if data.get("session") != os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", ""):
        return {}
    return {address: entry for address, entry in data.get("windows", {}).items()
            if address in clients and clients[address].get("pid") == entry.get("pid")
            and clients[address].get("workspace", {}).get("name") == WORKSPACE}


def restore(client, entries):
    address = client["address"]
    entry = entries.get(address)
    if entry:
        workspace = entry["workspace"]
        target = workspace["name"] if workspace["name"].startswith("special:") else (
            str(workspace["id"]) if workspace["name"] == str(workspace["id"]) else "name:" + workspace["name"])
    else:
        # Recover windows parked here before a shell reload, even if their origin is unavailable.
        active = ipc("activeworkspace", json_result=True)
        target = str(active["id"]) if active.get("id", 0) > 0 else "1"
    dispatch('hl.dsp.window.move({workspace=' + quote(target) + ',follow=true,window=' + quote("address:" + address) + '})')
    dispatch('hl.dsp.focus({window=' + quote("address:" + address) + '})')
    entries.pop(address, None)
    write(entries)


def run(action, address=None):
    clients = {client["address"]: client for client in ipc("clients", json_result=True)}
    entries = load(clients)
    if action == "status":
        write(entries)
    elif action == "restore-all":
        for client in clients.values():
            if client.get("workspace", {}).get("name") == WORKSPACE:
                restore(client, entries)
    else:
        if not address or not re.fullmatch(r"0x[0-9a-fA-F]+", address) or address not in clients:
            raise ValueError("The window is no longer available")
        client = clients[address]
        hidden = client.get("workspace", {}).get("name") == WORKSPACE
        if hidden:
            restore(client, entries)
        elif action == "restore":
            dispatch('hl.dsp.focus({window=' + quote("address:" + address) + '})')
        elif action == "toggle" and ipc("activewindow", json_result=True).get("address") != address:
            dispatch('hl.dsp.focus({window=' + quote("address:" + address) + '})')
        else:
            if client.get("pinned") or client.get("grouped"):
                raise ValueError("Unpin or ungroup this window before minimizing it")
            entries[address] = dict(pid=client["pid"], workspace=client["workspace"], monitor=client.get("monitor"))
            write(entries)  # Save the origin before moving; a shell reload must not lose it.
            dispatch('hl.dsp.window.move({workspace=' + quote(WORKSPACE) + ',follow=false,window=' + quote("address:" + address) + '})')
    # Read the compositor again rather than treating a dispatched request as completed.
    current = ipc("clients", json_result=True)
    return dict(ok=True, minimized=[client["address"] for client in current if client.get("workspace", {}).get("name") == WORKSPACE])


if __name__ == "__main__":
    try:
        action = sys.argv[1] if len(sys.argv) > 1 else "status"
        if action not in ("status", "toggle", "minimize", "restore", "restore-all"):
            raise ValueError("Unknown minimization action")
        STATE.parent.mkdir(parents=True, exist_ok=True)
        with STATE.with_suffix(".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            response = run(action, sys.argv[2] if len(sys.argv) > 2 else None)
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as error:
        response = dict(ok=False, error=str(error))
    print(json.dumps(response))
    sys.exit(0 if response["ok"] else 1)
