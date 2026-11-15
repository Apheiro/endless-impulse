#!/usr/bin/env python3
"""JSON CLI; no privileged operations and no shell commands. Standard library only."""
import argparse
import json
import sys
from inventory import Inventory
from rules import DraftStore, preview


def dispatch(request, inventory=None, store=None):
    inventory = inventory or Inventory()
    store = store or DraftStore()
    action = request.get("action")
    if action == "snapshot": return {"snapshot": inventory.snapshot()}
    if action == "detail": return {"detail": inventory.detail(request.get("id"))}
    if action == "drafts": return {"drafts": store.list()}
    if action == "preview": return {"preview": preview(request.get("rule"))}
    if action in ("save", "delete", "restore"):
        return {"drafts": store.mutate(action, request.get("rule") if action == "save" else request.get("id"))}
    raise ValueError("unsupported-action")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", default='{"action":"snapshot"}')
    args = parser.parse_args()
    try:
        if len(args.request) > 32768: raise ValueError("request-too-large")
        request = json.loads(args.request)
        if not isinstance(request, dict): raise ValueError("invalid-request")
        result = {"ok": True, **dispatch(request)}
    except json.JSONDecodeError:
        result = {"ok": False, "error": "invalid-json"}
    except (ValueError, OSError, TypeError, KeyError) as error:
        # Stable error codes translated by the UI; no raw stderr or private paths.
        message = str(error) if isinstance(error, ValueError) else "backend-read-or-storage-failed"
        result = {"ok": False, "error": message}
    print(json.dumps(result, ensure_ascii=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
