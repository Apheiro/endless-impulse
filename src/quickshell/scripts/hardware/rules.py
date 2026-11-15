"""Own draft metadata only. This module cannot install or reload udev rules."""
import fcntl
import grp
import json
import os
import re
import stat
import tempfile
from pathlib import Path

SUBSYSTEMS = {"hidraw": r"hidraw[0-9]+|hidraw\*", "input": r"event[0-9]+|event\*",
              "tty": r"tty(?:USB|ACM)[0-9]+|tty(?:USB|ACM)\*", "usb": r"[0-9]+-[0-9]+(?:\.[0-9]+)*"}
FIELDS = {"id", "label", "subsystem", "kernel", "vendor", "product", "uaccess", "mode", "group", "enabled"}


def validate(rule):
    if not isinstance(rule, dict) or set(rule) - FIELDS:
        raise ValueError("invalid-rule-fields")
    result = dict(rule)
    for key in ("id", "subsystem", "kernel", "vendor", "product"):
        if not isinstance(result.get(key), str): raise ValueError("invalid-rule-fields")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,47}", str(result.get("id", ""))):
        raise ValueError("invalid-rule-id")
    label = result.get("label", "")
    if not isinstance(label, str) or len(label) > 120 or any(ord(c) < 32 for c in label):
        raise ValueError("invalid-label")
    subsystem = result.get("subsystem", "")
    if subsystem not in SUBSYSTEMS or not re.fullmatch(SUBSYSTEMS[subsystem], str(result.get("kernel", ""))):
        raise ValueError("unsupported-subsystem-or-kernel")
    for key in ("vendor", "product"):
        if not re.fullmatch(r"[0-9a-f]{4}", str(result.get(key, ""))):
            raise ValueError("exact-usb-ids-required")
    for key in ("uaccess", "enabled"):
        if type(result.get(key)) is not bool:
            raise ValueError("invalid-rule-boolean")
    if result.get("mode", "") not in ("", "0600", "0660"):
        raise ValueError("unsafe-mode")
    group = result.get("group", "")
    if not isinstance(group, str) or (group and not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", group)):
        raise ValueError("invalid-group")
    if group:
        try: grp.getgrnam(group)
        except KeyError: raise ValueError("group-not-found") from None
    if not result["uaccess"] and not result.get("mode") and not group:
        raise ValueError("rule-action-required")
    return {**result, "mode": result.get("mode", ""), "group": group, "label": label}


def preview(rule):
    rule = validate(rule)
    # ATTR on the USB device itself, ATTRS on descendant interfaces. Both IDs
    # are deliberately tested at the same ancestor, never on unrelated parents.
    attr = "ATTR" if rule["subsystem"] == "usb" else "ATTRS"
    clauses = [f'SUBSYSTEM=="{rule["subsystem"]}"', f'KERNEL=="{rule["kernel"]}"',
               f'{attr}{{idVendor}}=="{rule["vendor"]}"', f'{attr}{{idProduct}}=="{rule["product"]}"']
    if rule["uaccess"]: clauses.append('TAG+="uaccess"')
    if rule["mode"]: clauses.append(f'MODE="{rule["mode"]}"')
    if rule["group"]: clauses.append(f'GROUP="{rule["group"]}"')
    return dict(rule=rule, filename=f'70-endless-impulse-{rule["id"]}.rules',
                content="# Managed by Endless Impulse\n" + ", ".join(clauses) + "\n",
                installation="privileged-installation-pending", activeOnHost=False,
                scope="all-matching-usb-units-and-selected-interface-class")


class DraftStore:
    def __init__(self, root=None):
        state = Path(os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local/state"))
        self.root = Path(root) if root is not None else state / "endless-Impulse/hardware"
        if not self.root.is_absolute(): raise ValueError("unsafe-draft-path")

    def _read_file(self, name, missing_ok=False):
        for part in (self.root, *self.root.parents):
            if part.is_symlink(): raise ValueError("unsafe-draft-path")
        path = self.root / name
        if path.is_symlink(): raise ValueError("unsafe-draft-path")
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            if missing_ok: return []
            raise ValueError("backup-unavailable") from None
        with os.fdopen(fd) as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
                raise ValueError("unsafe-draft-path")
            if info.st_size > 262144: raise ValueError("draft-store-too-large")
            try: data = json.loads(stream.read(262145))
            except (json.JSONDecodeError, UnicodeError):
                raise ValueError("invalid-draft-store") from None
        if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("rules"), list):
            raise ValueError("invalid-draft-store")
        rules = [validate(item) for item in data["rules"]]
        if len(rules) > 100 or len({r["id"] for r in rules}) != len(rules):
            raise ValueError("invalid-draft-store")
        return rules

    def _read(self):
        return self._read_file("drafts.json", missing_ok=True)

    def list(self):
        return [preview(rule) for rule in self._read()]

    def _write(self, name, rules):
        target = self.root / name
        if target.is_symlink(): raise ValueError("unsafe-draft-path")
        fd, temporary = tempfile.mkstemp(prefix=".draft-", dir=self.root)
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(dict(version=1, rules=rules), stream, ensure_ascii=True, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
            directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
            try: os.fsync(directory)
            finally: os.close(directory)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)

    def mutate(self, action, payload):
        if action not in ("save", "delete", "restore"): raise ValueError("unsupported-draft-operation")
        # This is a per-user draft directory, never a rules.d directory. Refuse
        # symlink components rather than following an unexpected storage redirect.
        for part in (self.root, *self.root.parents):
            if part.is_symlink(): raise ValueError("unsafe-draft-path")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.root.stat().st_uid != os.getuid(): raise ValueError("unsafe-draft-owner")
        fd = os.open(self.root / ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            rules = self._read()
            if action == "save":
                rule = validate(payload)
                updated = [r for r in rules if r["id"] != rule["id"]] + [rule]
                if len(updated) > 100: raise ValueError("too-many-drafts")
            elif action == "delete":
                if not isinstance(payload, str) or not any(r["id"] == payload for r in rules):
                    raise ValueError("draft-not-found")
                updated = [r for r in rules if r["id"] != payload]
            else:
                updated = self._read_file("previous.json")
            self._write("previous.json", rules)
            self._write("drafts.json", updated)
            if self._read() != updated: raise ValueError("draft-postcheck-failed")
            return self.list()
