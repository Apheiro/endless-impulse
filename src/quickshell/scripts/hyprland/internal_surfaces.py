#!/usr/bin/env python3
"""Exact auxiliary-window policy. Never manages processes or user minimization."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

WORKSPACE = "special:endless-internal"
BUILTIN = dict(id="xembed", windowClass="xembedsniproxy", title="",
               purpose="XEmbed → StatusNotifier: legacy tray icons", enabled=True, builtin=True)
STATE = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "endless-Impulse/internal-surfaces.json"
CRITICAL = re.compile(r"hypr|quickshell|endless|plasmashell|kwin|ksmserver|polkit|authentication|pinentry|gcr|lock|desktop|portal|session|sway|waybar|wlogout", re.I)
COMMON_MAIN_CLASSES = {"foot", "kitty", "alacritty", "wezterm", "firefox", "chromium", "google-chrome",
                       "code", "codium", "pamac-manager", "thunar", "nemo", "org.kde.dolphin", "org.gnome.nautilus"}


def quote(value):
    return '"' + ''.join('\\' + format(ord(c), '03d') if ord(c) < 32 else '\\' + c if c in '\\"' else c for c in str(value)) + '"'


def rules(config):
    if not isinstance(config, dict) or type(config.get("xembedEnabled", True)) is not bool:
        raise ValueError("Invalid internal surface preferences")
    manual = config.get("rules", [])
    if not isinstance(manual, list) or len(manual) > 32:
        raise ValueError("At most 32 manual rules are allowed")
    result = [dict(BUILTIN, enabled=config.get("xembedEnabled", True))]
    seen = set()
    for entry in manual:
        if not isinstance(entry, dict):
            raise ValueError("Invalid manual rule")
        cls, title, purpose = (entry.get(key, "") for key in ("windowClass", "title", "purpose"))
        if not isinstance(cls, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,127}", cls):
            raise ValueError("Use an exact class (3–128 letters, digits, dots, underscores or hyphens), without patterns")
        if cls.lower() == BUILTIN["windowClass"] or cls.lower() in COMMON_MAIN_CLASSES or CRITICAL.search(cls):
            raise ValueError("This class is integrated or protected")
        for value, maximum in ((title, 160), (purpose, 240)):
            if not isinstance(value, str) or not value.strip() or len(value) > maximum or any(ord(c) < 32 for c in value):
                raise ValueError("An exact title and a purpose are required, without control characters")
        if CRITICAL.search(title):
            raise ValueError("Authentication, desktop and shell windows are protected")
        key = (cls.lower(), title)
        if key in seen:
            raise ValueError("Duplicate class and title")
        seen.add(key)
        if type(entry.get("enabled", True)) is not bool:
            raise ValueError("Invalid enabled state")
        identity = hashlib.sha256((cls + "\0" + title).encode()).hexdigest()[:20]
        result.append(dict(id=identity, windowClass=cls, title=title, purpose=purpose,
                           enabled=entry.get("enabled", True), builtin=False))
    return result


def matches(entry, client):
    return (client.get("class") == entry["windowClass"]
            and (entry["builtin"] or client.get("title") == entry["title"])
            and client.get("floating") is True
            and (not entry["builtin"] or client.get("xwayland") is True))


def eligible(client):
    return (client.get("mapped") is True and not client.get("pinned") and not client.get("grouped")
            and not client.get("fullscreen") and not client.get("fullscreenClient")
            and client.get("workspace", {}).get("id", 0) > 0)


def rule_code(entry, enabled=None):
    # Lua's matcher calls this "float"; clients JSON calls it "floating".
    # Keep both the native restriction and matches()'s Python guard.
    match = 'class=' + quote("^" + re.escape(entry["windowClass"]) + "$") + ',float=true'
    if entry["builtin"]:
        match += ',xwayland=true'
    else:
        match += ',title=' + quote("^" + re.escape(entry["title"]) + "$")
    return ('hl.window_rule({name=' + quote("endless-internal-" + entry["id"])
            + ',enabled=' + str(entry["enabled"] if enabled is None else enabled).lower()
            + ',match={' + match + '},workspace=' + quote(WORKSPACE + " silent")
            + ',no_focus=true,no_initial_focus=true,focus_on_activate=false,render_unfocused=true})')


def ipc(*args, json_result=False):
    response = subprocess.run(["hyprctl", *args], capture_output=True, text=True, timeout=5)
    if response.returncode:
        raise ValueError(response.stderr.strip() or response.stdout.strip() or "Hyprland unavailable")
    if json_result:
        return json.loads(response.stdout)
    if response.stdout.strip() != "ok":
        raise ValueError(response.stdout.strip() or "Hyprland did not confirm the operation")


def evaluate(code):
    ipc("-r", "eval", code)


def save(state, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as target:
        temporary = Path(target.name)
        try:
            json.dump(state, target)
            target.flush()
            os.fsync(target.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    temporary.replace(path)


def load(path):
    state = json.loads(path.read_text()) if path.exists() else {}
    if state.get("session") != os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", ""):
        return dict(session=os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", ""), origins={}, rules=[])
    return state


def same_surface(client, origin):
    return (client.get("pid"), client.get("class"), client.get("initialTitle"), client.get("stableId")) == (
        origin.get("pid"), origin.get("class"), origin.get("initialTitle"), origin.get("stableId"))


def workspace_target(workspace):
    return str(workspace["id"]) if workspace["name"] == str(workspace["id"]) else "name:" + workspace["name"]


def origin_for(client, workspace=None):
    result = {key: client.get(key) for key in (
        "pid", "class", "initialTitle", "stableId", "workspace", "at", "size", "monitor")}
    if workspace is not None:
        result["workspace"] = workspace
    return result


def move(client, target):
    evaluate('hl.dispatch(hl.dsp.window.move({workspace=' + quote(target)
             + ',follow=false,window=' + quote("address:" + client["address"]) + '}))')


def reconcile(config, path=STATE):
    entries = rules(config)  # Validate everything before any mutation.
    clients = ipc("-j", "clients", json_result=True)
    state = load(path)
    origins = state["origins"]
    by_address = {client["address"]: client for client in clients}
    for address, origin in list(origins.items()):
        if address not in by_address or not same_surface(by_address[address], origin):
            origins.pop(address)
    active = {entry["id"] for entry in entries if entry["enabled"]}
    # Named rules survive shell reloads; explicitly disable removed policies.
    previous = state["rules"]
    # Journal the union before installing rules so partial IPC failures are recoverable.
    state["rules"] = list({entry["id"]: entry for entry in [*previous, *entries]}.values())
    save(state, path)
    for old in previous:
        if old["id"] not in active:
            evaluate(rule_code(old, False))
    for entry in entries:
        evaluate(rule_code(entry))
    state["rules"] = entries
    save(state, path)
    errors = []
    for client in clients:
        address = client["address"]
        origin = origins.get(address)
        hidden = client.get("workspace", {}).get("name") == WORKSPACE
        selected = next((e for e in entries if e["enabled"] and matches(e, client)), None)
        try:
            known = next((e for e in [*entries, *previous] if matches(e, client)), None)
            if not selected and (origin or (hidden and known)):
                if hidden:
                    # A native spawn rule can route a surface before its origin is observable.
                    workspace = origin["workspace"] if origin else ipc("-j", "activeworkspace", json_result=True)
                    if workspace.get("id", 0) <= 0:
                        # Keep the old policy as recovery identity when no destination exists.
                        state["rules"] = list({e["id"]: e for e in [*previous, *entries]}.values())
                        save(state, path)
                        raise ValueError("Select an ordinary workspace before restoring this surface")
                    if not origin:
                        origins[address] = origin_for(client, workspace)
                        save(state, path)
                    move(client, workspace_target(workspace))
                    restored = next((c for c in ipc("-j", "clients", json_result=True) if c["address"] == address), None)
                    if restored and restored.get("workspace", {}).get("name") == WORKSPACE:
                        raise ValueError("Restoration was not confirmed; use Retry")
                origins.pop(address, None)
                save(state, path)
            elif selected and not hidden and eligible(client):
                # Save before moving; failures retain a recoverable origin.
                origins[address] = origin_for(client)
                save(state, path)
                move(client, WORKSPACE)
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            errors.append(address + ": " + str(error))
    current = ipc("-j", "clients", json_result=True)
    current_by_address = {client["address"]: client for client in current}
    for address, origin in origins.items():
        client = current_by_address.get(address)
        if client and same_surface(client, origin) and any(e["enabled"] and matches(e, client) for e in entries):
            if client.get("workspace", {}).get("name") != WORKSPACE:
                errors.append(address + ": workspace move was not confirmed; use Retry")
    return dict(ok=not errors, error="\n".join(errors), entries=entries, clients=current)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("validate", "apply", "restore-xembed"))
    parser.add_argument("--config", default='{}')
    parser.add_argument("--state", type=Path, default=STATE)
    args = parser.parse_args()
    try:
        config = json.loads(args.config)
        if args.action == "restore-xembed":
            config = dict(xembedEnabled=False, rules=[])
            # This recovery action only accepts a state containing the builtin.
            if any(not e.get("builtin") for e in load(args.state)["rules"]):
                raise ValueError("Use Settings to restore manual entries separately")
        if args.action == "validate":
            response = dict(ok=True, entries=rules(config))
        else:
            args.state.parent.mkdir(parents=True, exist_ok=True)
            with args.state.with_suffix(".lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                response = reconcile(config, args.state)
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
        response = dict(ok=False, error=str(error))
    print(json.dumps(response))
    return 0 if response["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
