#!/usr/bin/env python3
"""Query the explicit Arch dependency manifest without sourcing build scripts."""
import argparse
import json
from pathlib import Path
import subprocess

MANIFEST = Path(__file__).parent / "dependencies/arch.json"


def packages(origin):
    data = json.loads(MANIFEST.read_text())
    if origin == "all":
        return sorted(set(data["repository"] + data["aur"]))
    return data[origin]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("origin", choices=["repository", "aur", "all", "legacy_packages"])
    parser.add_argument("--missing", action="store_true", help="Check installed package names and providers")
    args = parser.parse_args()
    requested = packages(args.origin)
    if args.missing:
        result = subprocess.run(["pacman", "-T", *requested], text=True, capture_output=True)
        if result.returncode not in (0, 127):
            raise SystemExit(result.stderr or result.returncode)
        requested = result.stdout.splitlines()
    if requested:
        print("\n".join(requested))
