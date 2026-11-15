#!/usr/bin/env python3
"""Route Hyprland IPC to the active desktop, including repository/Nix instances."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import runpy
import tempfile


def context_path():
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "dots-hyperland/runtime.json"


def register(config, executable):
    config = Path(config).resolve()
    if config.is_file():
        config = config.parent
    executable = shutil.which(executable)
    if not (config / "shell.qml").is_file() or not executable:
        raise ValueError("Cannot register the desktop configuration or Quickshell executable.")
    path = context_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as output:
        json.dump({"config": str(config), "executable": str(Path(executable).resolve()),
                   "launcher": os.environ.get("DOTS_SHELL_LAUNCHER", "")}, output)
        temporary = Path(output.name)
    temporary.replace(path)


def read_context():
    context = json.loads(context_path().read_text())
    config, executable = Path(context["config"]), Path(context["executable"])
    if not config.is_absolute() or not executable.is_absolute() or not executable.is_file():
        raise ValueError("The active desktop context is invalid. Restart it with ./dev restart.")
    return context


def ipc_command(arguments):
    context = read_context()
    return [context["executable"], "-p", context["config"], "ipc", "call", *arguments]


def main(arguments):
    if len(arguments) == 3 and arguments[0] == "register":
        register(*arguments[1:])
        return 0
    if arguments == ["health"]:
        result = subprocess.run(ipc_command(["health", "ping"]), capture_output=True, text=True, timeout=3)
        return result.returncode
    if len(arguments) >= 2 and arguments[0] == "ipc":
        return subprocess.run(ipc_command(arguments[1:]), timeout=10).returncode
    if arguments == ["stop"]:
        context = read_context()
        return subprocess.run([context["executable"], "-p", context["config"], "kill"], timeout=10).returncode
    if arguments == ["restart"] or arguments[:1] == ["settings"]:
        context = read_context()
        config = Path(context["config"])
        environment = dict(os.environ, DOTS_SHELL_SOURCE=str(config))
        if arguments[:1] == ["settings"] and len(arguments) > 1:
            section = arguments[1]
            existing = subprocess.run([context["executable"], "-p", str(config / "settings.qml"), "ipc", "call", "settings", "page", section], capture_output=True, timeout=3)
            if existing.returncode == 0: return 0
            environment["DOTS_SETTINGS_PAGE"] = section
        branding = Path(config) / "scripts/shell/branding.py"
        if branding.is_file():
            runpy.run_path(str(branding))["migrate"](environment)
        launcher = Path(context["launcher"]) if context.get("launcher") else None
        if arguments == ["restart"]:
            subprocess.run([context["executable"], "-p", config, "kill"], timeout=10, check=True)
            command = [str(launcher)] if launcher and launcher.is_file() else [context["executable"], "-p", config]
        else:
            launcher = launcher.with_name("dots-hyperland-settings") if launcher else None
            command = [str(launcher)] if launcher and launcher.is_file() else [context["executable"], "-p", str(Path(config) / "settings.qml")]
        return subprocess.run([*command, "--no-duplicate", "-d"], env=environment, timeout=15).returncode
    raise ValueError("Usage: dots-shell health | ipc TARGET FUNCTION [ARGS...] | stop | restart | settings")


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        if sys.argv[1:] != ["health"]:
            print(f"[Desktop IPC] {error}", file=sys.stderr)
        sys.exit(1)
