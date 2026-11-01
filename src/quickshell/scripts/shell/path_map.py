#!/usr/bin/env python3
"""Describe explicitly registered desktop paths without scanning their contents."""
import json
import os
from pathlib import Path
import sys
from urllib.parse import unquote, urlparse


def normalize(value):
    if value.startswith("file:"):
        value = unquote(urlparse(value).path)
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError("Installation paths must be absolute.")
    return Path(os.path.normpath(path))


def build(records):
    nodes, groups = {}, {}
    for record in records:
        if not record.get("path"):
            continue
        path = normalize(record["path"])
        key = str(path)
        if key in nodes:
            node = nodes[key]
            node["tags"] = list(dict.fromkeys(node["tags"] + record.get("tags", [])))
            if record["description"] not in node["uses"]:
                node["uses"].append(record["description"])
            continue
        group = record["group"]
        groups.setdefault(group, {"id": "group:" + group, "title": record["groupTitle"], "icon": record["groupIcon"], "path": "", "children": [], "tags": [], "uses": []})
        exists = path.exists()
        nodes[key] = {"id": key, "path": key, "title": record["title"], "description": record["description"],
                      "uses": [record["description"]], "tags": list(dict.fromkeys(record.get("tags", []))),
                      "group": group, "kind": record.get("kind", "directory"), "exists": exists,
                      "target": str(path.resolve()), "children": [], "icon": record.get("icon", "folder")}
    # Attach each path only to its nearest registered directory, never to a file.
    for key, node in nodes.items():
        parent = next((nodes[str(path)] for path in Path(key).parents
                       if str(path) in nodes and nodes[str(path)]["kind"] == "directory"
                       and nodes[str(path)]["group"] == node["group"]), groups[node["group"]])
        parent["children"].append(node)
    return list(groups.values())


def main():
    try:
        result = {"ok": True, "groups": build(json.load(sys.stdin))}
    except (ValueError, KeyError, OSError, TypeError) as error:
        result = {"ok": False, "error": str(error)}
    print(json.dumps(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
