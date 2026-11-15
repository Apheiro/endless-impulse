#!/usr/bin/env python3
"""Move local preferences to Endless Impulse, retaining legacy path aliases."""
import os
from pathlib import Path


def migrate_directory(base):
    current = Path(base) / "endless-Impulse"
    if current.exists() or current.is_symlink():
        return
    legacy = next((Path(base) / name for name in ("artificial-impulse", "illogical-impulse")
                   if (Path(base) / name).is_dir()), None)
    if legacy is None:
        return
    if legacy.is_symlink():
        current.symlink_to(legacy.resolve(), target_is_directory=True)
        return
    legacy.rename(current)
    try:
        legacy.symlink_to(current.name, target_is_directory=True)
    except OSError:
        current.rename(legacy)
        raise


def migrate(environment=None):
    environment = os.environ if environment is None else environment
    home = Path(environment.get("HOME", Path.home()))
    for variable, fallback in (("XDG_CONFIG_HOME", home / ".config"),
                               ("XDG_STATE_HOME", home / ".local/state"),
                               ("XDG_DATA_HOME", home / ".local/share")):
        migrate_directory(environment.get(variable, fallback))


if __name__ == "__main__":
    migrate()
