#!/usr/bin/env python3
"""Connect a Nix GUI to host NVIDIA userspace libraries without importing host Qt."""
import hashlib
import configparser
import json
import os
from pathlib import Path
import sys
import runpy


def icon_environment(environment):
    if environment.get("QS_ICON_THEME"):
        return environment
    config = Path(environment.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "kdeglobals"
    preferences = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        preferences.read(config)
        theme = preferences.get("Icons", "Theme", fallback="breeze")
    except configparser.Error:
        theme = "breeze"
    directories = environment.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":")
    directories.insert(0, environment.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    if "/" in theme or not any((Path(path) / "icons" / theme / "index.theme").exists() for path in directories):
        theme = "breeze"
    return dict(environment, QS_ICON_THEME=theme)


def nvidia_environment(environment, library_dirs):
    driver = next((directory / "libEGL_nvidia.so.0" for directory in library_dirs
                   if (directory / "libEGL_nvidia.so.0").exists()), None)
    if driver is None:
        raise RuntimeError("NVIDIA is active but its EGL library was not found. Set DOTS_NVIDIA_LIBDIR to its directory.")
    driver = driver.resolve()
    token = hashlib.sha256(str(driver).encode()).hexdigest()[:16]
    cache = Path(environment.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "dots-hyperland/graphics" / token
    libraries, platforms, gbm = cache / "lib", cache / "platforms", cache / "gbm"
    for directory in (libraries, platforms, gbm):
        directory.mkdir(parents=True, exist_ok=True)

    def link(source, target):
        if target.is_symlink():
            if target.resolve() == source.resolve():
                return
            target.unlink()
        if not target.exists():
            target.symlink_to(source.resolve())

    for directory in library_dirs:
        for pattern in ("libnvidia*.so*", "libEGL_nvidia.so*", "libGLX_nvidia.so*"):
            for source in directory.glob(pattern):
                if source.exists():
                    link(source, libraries / source.name)
        for source in (directory / "gbm").glob("nvidia*_gbm.so"):
            if source.exists():
                link(source, gbm / source.name)
    vendor = cache / "nvidia.json"
    vendor.write_text(json.dumps({"file_format_version": "1.0.0", "ICD": {"library_path": str(driver)}}))
    for directory in (Path("/usr/share/egl/egl_external_platform.d"), Path("/etc/egl/egl_external_platform.d")):
        for source in directory.glob("*nvidia*.json"):
            data = json.loads(source.read_text())
            name = Path(data.get("ICD", {}).get("library_path", "")).name
            target = libraries / name
            if name and target.exists():
                data["ICD"]["library_path"] = str(target)
                (platforms / source.name).write_text(json.dumps(data))
    previous = environment.get("LD_LIBRARY_PATH", "")
    return dict(environment,
                LD_LIBRARY_PATH=str(libraries) + (":" + previous if previous else ""),
                __EGL_VENDOR_LIBRARY_FILENAMES=str(vendor),
                __EGL_EXTERNAL_PLATFORM_CONFIG_DIRS=str(platforms),
                GBM_BACKENDS_PATH=str(gbm))


def main():
    if len(sys.argv) < 2:
        raise RuntimeError("Expected the GUI command to launch.")
    environment = icon_environment(dict(os.environ))
    source = environment.get("DOTS_SHELL_SOURCE")
    branding = Path(source) / "scripts/shell/branding.py" if source else None
    if branding and branding.is_file():
        runpy.run_path(str(branding))["migrate"](environment)
    # NixOS already supplies its own graphics bridge. Mesa uses the bundled paths.
    manage = (environment.get("DOTS_HOST_GRAPHICS", "auto") != "off"
              and not Path("/run/opengl-driver/lib").exists())
    if manage and Path("/proc/driver/nvidia/version").exists():
        directories = [Path(p) for p in (
            environment.get("DOTS_NVIDIA_LIBDIR", "/usr/lib"), "/usr/lib64",
            "/usr/lib/x86_64-linux-gnu", "/usr/lib/aarch64-linux-gnu",
            "/lib/x86_64-linux-gnu")]
        environment = nvidia_environment(environment, directories)
    elif manage:
        for variable, setting in (("__EGL_VENDOR_LIBRARY_FILENAMES", "DOTS_MESA_VENDOR"),
                                  ("LIBGL_DRIVERS_PATH", "DOTS_MESA_DRIVERS"),
                                  ("GBM_BACKENDS_PATH", "DOTS_MESA_GBM")):
            if environment.get(setting):
                environment.setdefault(variable, environment[setting])
    os.execvpe(sys.argv[1], sys.argv[1:], environment)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError) as error:
        print(f"[Host graphics] {error}", file=sys.stderr)
        sys.exit(1)
