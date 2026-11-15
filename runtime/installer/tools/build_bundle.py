#!/usr/bin/env python3
"""Prepare the experimental exact-file subset, never install it or run its scripts."""
import argparse
import hashlib
import json
from pathlib import Path
import stat

CRATE = Path(__file__).resolve().parents[1]
REPO = CRATE.parents[1]
# Explicit allowlist. No recursive walk of Quickshell, the submodule, target or HOME.
PAYLOAD = [
    ("src/quickshell/modules/shared/functions/ShortcutSymbols.js", "quickshell_config", "modules/shared/functions/ShortcutSymbols.js", "managed"),
    ("src/quickshell/scripts/shell/control.py", "runtime", "scripts/shell/control.py", "managed"),
    ("config/xdg/config/hypr/hyprland/services/shortcuts.lua", "hypr_config", "hyprland/services/shortcuts.lua", "managed"),
    ("config/xdg/config/hypr/hyprland/services/desktop.lua", "hypr_config", "hyprland/services/desktop.lua", "managed"),
    ("config/xdg/config/hypr/hyprland/keybinds.lua", "hypr_config", "hyprland/keybinds.lua", "managed"),
    ("config/xdg/config/hypr/custom/keybinds.lua", "hypr_config", "custom/keybinds.lua", "user"),
    ("config/xdg/data/icons/illogical-impulse.svg", "data", "icons/illogical-impulse.svg", "managed"),
]
ASSETS = [
    ("installer/dependencies/arch.json", "assets/arch-dependencies.json", "arch_dependencies"),
    ("packaging/nix/services/arch.json", "assets/host-services.json", "services_reference"),
    ("LICENSE", "assets/LICENSE", "license"),
]


def safe_source(relative):
    path = REPO / relative
    for part in [path, *path.parents]:
        if part.is_symlink():
            raise ValueError(f"Refusing symlink source: {relative}")
        if part == REPO:
            break
    metadata = path.stat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise ValueError(f"Source must be a single-link regular file: {relative}")
    return path.read_bytes()


def write_new(root, relative, data):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New or empty output directory under /tmp or runtime/installer/bundle")
    parser.add_argument("--version", default="0.1.0-subset")
    args = parser.parse_args()
    output = args.output.absolute()
    if output != output.resolve() or any(p.is_symlink() for p in [output, *output.parents]):
        parser.error("Output must be canonical and symlink-free")
    allowed = output.is_relative_to(Path('/tmp')) and output != Path('/tmp')
    allowed = allowed or output == CRATE / 'bundle'
    home = Path.home().resolve()
    if not allowed or output.is_relative_to(home) and output != CRATE / 'bundle':
        parser.error("Only /tmp or this crate's dedicated bundle directory is allowed")
    if output.exists() and any(not p.is_dir() or p.is_symlink() for p in output.rglob('*')):
        parser.error("Output is not empty; existing bundles are never overwritten")
    # Validate and snapshot every source BEFORE creating the output.
    sources = [(row, safe_source(row[0])) for row in PAYLOAD]
    assets = [(row, safe_source(row[0])) for row in ASSETS]
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    manifest = {"schema": 1, "payload_version": args.version, "completeness": "subset", "dependencies": "not_implemented", "services": "not_implemented", "files": [], "assets": []}
    for index, ((source, category, destination, ownership), data) in enumerate(sources):
        name = f"payload/{index:02}-{Path(source).name}"
        write_new(output, name, data)
        manifest['files'].append({"source": name, "category": category, "destination": destination, "sha256": hashlib.sha256(data).hexdigest(), "ownership": ownership, "mode": 0o644})
    for (_, name, role), data in assets:
        write_new(output, name, data)
        manifest['assets'].append({"source": name, "sha256": hashlib.sha256(data).hexdigest(), "role": role})
    write_new(output, 'manifest.json', (json.dumps(manifest, indent=2) + '\n').encode())
    print(f"Prepared {len(sources)}-file EXPERIMENTAL SUBSET at {output}. No desktop installed.")


if __name__ == '__main__':
    main()
