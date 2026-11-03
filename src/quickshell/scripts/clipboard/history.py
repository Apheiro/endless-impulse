#!/usr/bin/env python3
"""Cliphist plus durable saved items; payloads never pass through a shell."""
from contextlib import contextmanager
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

DIRECTORY = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "artificial-impulse/clipboard"
INDEX = DIRECTORY / "saved.json"
BINARY = os.environ.get("DOTS_CLIPHIST_BINARY", "cliphist")
SAVED_ID = re.compile(r"saved-([0-9a-f]{64})\Z")


@contextmanager
def locked():
    DIRECTORY.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(DIRECTORY / ".lock", "a", opener=lambda path, flags: os.open(path, flags, 0o600)) as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def atomic(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
        temporary = Path(output.name)
        output.write(payload)
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(path)


def saved():
    data = json.loads(INDEX.read_text()) if INDEX.exists() else {"version": 1, "items": []}
    if data.get("version") != 1 or not isinstance(data.get("items"), list):
        raise ValueError("Could not read saved clipboard items")
    for item in data["items"]:
        if not SAVED_ID.fullmatch(item.get("id", "")) or not isinstance(item.get("summary"), str):
            raise ValueError("Invalid saved clipboard index")
    return data["items"]


def persist(items):
    atomic(INDEX, json.dumps({"version": 1, "items": items}, ensure_ascii=False).encode())


def cliphist(action, payload=None):
    result = subprocess.run([BINARY, action], input=payload, capture_output=True, timeout=15)
    if action == "list" and b"please store something first" in result.stderr:
        return b""
    if result.returncode:
        raise ValueError("Clipboard history operation failed; the entry may no longer exist")
    return result.stdout


def identifier(value):
    value = str(value).split("\t", 1)[0]
    if not value.isdecimal() and not SAVED_ID.fullmatch(value):
        raise ValueError("Invalid clipboard entry")
    return value


def payload_path(value):
    match = SAVED_ID.fullmatch(value)
    if not match:
        raise ValueError("Invalid saved clipboard entry")
    return DIRECTORY / (match[1] + ".bin")


def decode(value):
    value = identifier(value)
    if SAVED_ID.fullmatch(value):
        if not any(item["id"] == value for item in saved()):
            raise ValueError("This saved clipboard item no longer exists")
        return payload_path(value).read_bytes()
    return cliphist("decode", value.encode())


def snapshot():
    items = saved()
    summaries = {item["summary"] for item in items}
    digests = {item["id"][6:] for item in items}
    history = []
    chronological = cliphist("list").decode("utf-8", errors="replace").splitlines()
    for line in chronological:
        key, separator, summary = line.partition("\t")
        if not separator or not key.isdecimal():
            continue
        # Only decode candidates that look like a saved item. This removes
        # duplicates even after recopying or rebuilding cliphist's database.
        if summary in summaries:
            try:
                if hashlib.sha256(decode(key)).hexdigest() in digests:
                    continue
            except ValueError:
                continue  # The external clipboard watcher may have evicted it.
        history.append(line)
    return dict(entries=[item["id"] + "\t" + item["summary"] for item in items] + history,
                pinned=[item["id"] for item in items], removableCount=len(history), historyEntries=chronological)


def pin(value):
    value = identifier(value)
    if SAVED_ID.fullmatch(value):
        return
    line = next((line for line in cliphist("list").decode("utf-8", errors="replace").splitlines()
                 if line.partition("\t")[0] == value), None)
    if line is None:
        raise ValueError("This clipboard entry no longer exists")
    payload = decode(value)
    key = "saved-" + hashlib.sha256(payload).hexdigest()
    items = saved()
    if any(item["id"] == key for item in items):
        return
    atomic(payload_path(key), payload)
    persist([dict(id=key, summary=line.partition("\t")[2])] + items)


def unpin(value):
    value = identifier(value)
    payload = decode(value)
    # Put it back in the ordinary history before removing its durable copy.
    cliphist("store", payload)
    persist([item for item in saved() if item["id"] != value])
    payload_path(value).unlink(missing_ok=True)


def clear():
    # Never erase history if a saved item's durable copy cannot be read.
    for item in saved():
        payload = payload_path(item["id"]).read_bytes()
        if hashlib.sha256(payload).hexdigest() != item["id"][6:]:
            raise ValueError("A saved clipboard item could not be verified; history was not cleared")
    cliphist("wipe")


def copy(value):
    subprocess.run(["wl-copy"], input=decode(value), check=True, timeout=10)


def paste(value, delay=.05):
    copy(value)
    time.sleep(delay)
    subprocess.run(["ydotool", "key", "-d", "1", "29:1", "47:1", "47:0", "29:0"], check=True, timeout=10)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["list", "pin", "unpin", "delete", "clear", "decode", "cache", "copy", "paste", "superpaste"])
    parser.add_argument("entry", nargs="?")
    parser.add_argument("destination", nargs="?")
    args = parser.parse_args()
    with locked():
        if args.action in ("decode", "cache", "copy", "paste"):
            if args.action == "decode": sys.stdout.buffer.write(decode(args.entry))
            elif args.action == "cache": atomic(Path(args.destination), decode(args.entry))
            elif args.action == "copy": copy(args.entry)
            else: paste(args.entry)
            return
        data = json.load(sys.stdin) if args.action != "list" else {}
        if args.action == "pin": pin(data["entry"])
        elif args.action == "unpin": unpin(data["entry"])
        elif args.action == "clear": clear()
        elif args.action == "delete":
            key = identifier(data["entry"])
            if SAVED_ID.fullmatch(key): raise ValueError("Unsave this item before deleting it")
            cliphist("delete", key.encode())
        elif args.action == "superpaste":
            for key in reversed(data["entries"]): paste(key, max(0, min(1, float(data.get("delay", .05)))))
        print(json.dumps(dict(ok=True, **snapshot()), ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        # Never expose copied content or command input through diagnostics.
        print(json.dumps(dict(ok=False, error="Could not complete the clipboard operation. " +
                              (str(error) if isinstance(error, ValueError) else "Check the clipboard service."))))
        sys.exit(1)
