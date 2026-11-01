#!/usr/bin/env python3
"""User icon theme integration. No package-owned file is changed."""
import configparser
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

OVERLAY = "ArtificialImpulse"
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
DATA = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
STATE = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
STORE = CONFIG / "artificial-impulse/icons.json"
ROOT = DATA / "icons" / OVERLAY
EXTENSIONS = {".svg", ".png", ".xpm"}


def shares():
    return list(dict.fromkeys([DATA, *map(Path, os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":"))]))


def roots():
    return list(dict.fromkeys([DATA / "icons", Path.home() / ".icons", *[p / "icons" for p in shares()]]))


def ini(path):
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    try:
        parser.read(path, encoding="utf-8")
    except (configparser.Error, UnicodeError, OSError):
        pass
    return parser


def themes(include_hidden=False):
    found = {}
    for base in roots():
        if not base.is_dir():
            continue
        for path in sorted(base.iterdir()):
            if path.name in found or path.name == OVERLAY or not (path / "index.theme").is_file():
                continue
            info = ini(path / "index.theme")
            if not info.has_section("Icon Theme"):
                continue
            section = info["Icon Theme"]
            if (not include_hidden and section.get("Hidden", "false").lower() == "true") or not section.get("Directories"):
                continue
            found[path.name] = {"id": path.name, "name": section.get("Name", path.name), "path": str(path)}
    return sorted(found.values(), key=lambda t: t["name"].casefold())


def read_store():
    if STORE.exists():
        value = json.loads(STORE.read_text())
        if not isinstance(value, dict) or not isinstance(value.get("overrides", {}), dict):
            raise ValueError("Invalid icon preferences; open icons.json to correct them.")
        return value
    return {"theme": ini(CONFIG / "kdeglobals").get("Icons", "Theme", fallback="breeze"), "overrides": {}}


def fallback_themes(value, theme, installed=None):
    if not isinstance(value, list) or any(not isinstance(name, str) for name in value):
        raise ValueError("Backup icon themes must be a list of installed theme names.")
    result = []
    for name in value:
        if name in (theme, "hicolor") or name in result:
            continue
        if not name or name == OVERLAY or Path(name).name != name or "," in name or "\n" in name:
            raise ValueError("Invalid backup icon theme.")
        if installed is not None and name not in installed:
            raise ValueError(f"Backup icon theme is no longer installed: {name}")
        result.append(name)
    return result


def icon_map(theme, fallbacks=()):
    """Resolve at shell preview size; toolkits keep their own size-aware loaders."""
    result, visited = {}, set()

    def visit(name):
        if name in visited or not name or Path(name).name != name:
            return
        visited.add(name)
        parents = []
        locations = [base / name for base in roots() if (base / name).is_dir()]
        info = next((ini(p / "index.theme") for p in locations if (p / "index.theme").is_file()), None)
        directories = []
        if info and info.has_section("Icon Theme"):
            section = info["Icon Theme"]
            directories = list(dict.fromkeys((section.get("Directories", "") + "," + section.get("ScaledDirectories", "")).split(",")))
            parents = section.get("Inherits", "").split(",")
            def distance(directory):
                size = info.getint(directory, "Size", fallback=48)
                scalable = info.get(directory, "Type", fallback="") == "Scalable"
                return (0 if scalable else abs(size - 48), directory)
            directories = sorted(filter(None, directories), key=distance)
        # User hicolor app icons often exist without a local index.theme.
        if not directories and name == "hicolor":
            directories = ["scalable/apps", "48x48/apps", "64x64/apps", "128x128/apps", "256x256/apps", "32x32/apps", "16x16/apps"]
        for directory in directories:
            if Path(directory).is_absolute() or ".." in Path(directory).parts:
                continue
            for location in locations:
                folder = location / directory
                if folder.is_dir():
                    for file in sorted(folder.iterdir()):
                        if file.suffix.lower() in EXTENSIONS and file.is_file():
                            result.setdefault(file.stem, file.as_uri())
        for parent in parents:
            if parent.strip() != "hicolor":
                visit(parent.strip())
    if theme != "hicolor":
        visit(theme)
    for fallback in fallbacks:
        if fallback != "hicolor":
            visit(fallback)
    visit("hicolor")
    for share in shares():
        folder = share / "pixmaps"
        if folder.is_dir():
            for path in sorted(folder.iterdir()):
                if path.suffix.lower() in EXTENSIONS and path.is_file():
                    result.setdefault(path.stem, path.as_uri())
    return result


def applications():
    found = {}
    for share in shares():
        base = share / "applications"
        if not base.is_dir():
            continue
        for file in sorted(base.rglob("*.desktop")):
            identity = str(file.relative_to(base)).replace("/", "-")
            if identity in found:
                continue
            section = ini(file)
            if not section.has_section("Desktop Entry"):
                continue
            entry = section["Desktop Entry"]
            # Hidden desktop files shadow entries from lower priority roots.
            found[identity] = None
            if entry.get("Hidden", "false").lower() == "true" or entry.get("NoDisplay", "false").lower() == "true":
                continue
            icon = entry.get("Icon", "")
            if entry.get("Type", "Application") != "Application" or not icon:
                continue
            found[identity] = {"id": identity, "name": entry.get("Name", file.stem), "icon": icon, "wmClass": entry.get("StartupWMClass", ""), "file": str(file)}
    # Restore the logical original name for locally adapted absolute-path entries.
    for identity, override in read_store().get("overrides", {}).items():
        app = found.get(identity)
        if app and app["icon"] == override["path"]:
            app["icon"] = override["original"]
    return sorted(filter(None, found.values()), key=lambda a: a["name"].casefold())


def edit_ini(text, section, key, value):
    lines, inside, replaced, exists = text.splitlines(keepends=True), False, False, False
    output = []
    for line in lines:
        match = re.match(r"\s*\[([^]]+)\]\s*$", line)
        if match:
            if inside and not replaced:
                output.append(f"{key}={value}\n")
                replaced = True
            inside = match.group(1) == section
            exists |= inside
        if inside and re.match(r"\s*" + re.escape(key) + r"\s*=", line):
            if not replaced:
                output.append(f"{key}={value}\n")
                replaced = True
        else:
            output.append(line if line.endswith("\n") else line + "\n")
    if not replaced:
        if not exists:
            output.append(f"\n[{section}]\n")
        output.append(f"{key}={value}\n")
    return "".join(output)


def atomic(path, content):
    # Follow existing personal symlinks rather than silently replacing the link.
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".icons-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content if isinstance(content, bytes) else content.encode())
        if path.exists():
            os.chmod(temp, path.stat().st_mode & 0o777)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def targets():
    return [
        ("Qt / KDE", CONFIG / "kdeglobals", "Icons", "Theme"),
        ("GTK 3", CONFIG / "gtk-3.0/settings.ini", "Settings", "gtk-icon-theme-name"),
        ("GTK 4", CONFIG / "gtk-4.0/settings.ini", "Settings", "gtk-icon-theme-name"),
        ("Qt 5ct", CONFIG / "qt5ct/qt5ct.conf", "Appearance", "icon_theme"),
        ("Qt 6ct", CONFIG / "qt6ct/qt6ct.conf", "Appearance", "icon_theme"),
    ]


def legacy_targets():
    result = [("GTK 2", path, "gtk-icon-theme-name", "=") for path in
              (Path.home() / ".gtkrc-2.0", CONFIG / "gtk-2.0/gtkrc") if path.exists()]
    xsettings = CONFIG / "xsettingsd/xsettingsd.conf"
    if xsettings.exists():
        result.append(("XSettings", xsettings, "Net/IconThemeName", " "))
    return result


def edit_property(text, key, separator):
    line = f'{key}{separator}"{OVERLAY}"'
    expression = r"(?m)^\s*" + re.escape(key) + r"(?:\s*=|\s+)\s*[^\n]*$"
    return re.sub(expression, lambda _: line, text) if re.search(expression, text) else text.rstrip() + "\n" + line + "\n"


def color_paths():
    import tomllib
    paths = [("Shell preferences", CONFIG / "artificial-impulse/config.json"),
             ("Matugen", CONFIG / "matugen/config.toml"),
             ("Qt / KDE", CONFIG / "kdeglobals"),
             ("KDE color scheme (dark)", DATA / "color-schemes/MaterialYouDark.colors"),
             ("KDE color scheme (light)", DATA / "color-schemes/MaterialYouLight.colors"),
             ("Kitty", STATE / "quickshell/user/generated/terminal/kitty-theme.conf"),
             ("Terminal palette", STATE / "quickshell/user/generated/terminal/sequences.txt")]
    config = CONFIG / "matugen/config.toml"
    if config.exists():
        try:
            templates = tomllib.loads(config.read_text()).get("templates", {})
            for name, value in templates.items():
                output = value.get("output_path")
                if output:
                    paths.append((name, Path(output).expanduser()))
        except (OSError, ValueError):
            pass
    return [{"name": name, "path": str(path), "exists": path.exists()} for name, path in paths]


def snapshot():
    store = read_store()
    available = themes()
    base = store.get("theme", "breeze")
    fallbacks = fallback_themes(store.get("fallbacks", []), base)
    mapping = icon_map(OVERLAY if STORE.exists() and (ROOT / "index.theme").exists() else base, fallbacks)
    app_list = applications()
    aliases = {}
    for identity, override in store.get("overrides", {}).items():
        if Path(override["path"]).is_file():
            url = Path(override["path"]).as_uri()
            aliases[identity.removesuffix(".desktop")] = url
            app = next((a for a in app_list if a["id"] == identity), None)
            if app and app.get("wmClass"):
                aliases[app["wmClass"]] = url
    paths = [{"name": name, "path": str(path), "exists": path.exists(), "value": ini(path).get(section, key, fallback="—")} for name, path, section, key in targets()]
    paths += [{"name": name, "path": str(path), "exists": True} for name, path, _, _ in legacy_targets()]
    if (CONFIG / "dconf").exists():
        paths.append({"name": "GNOME / GSettings", "path": str(CONFIG / "dconf"), "exists": True})
    paths += [{"name": "Artificial Impulse", "path": str(STORE), "exists": STORE.exists()}, {"name": "Icon overlay", "path": str(ROOT / "index.theme"), "exists": (ROOT / "index.theme").exists()}]
    paths += [{"name": "Application · " + Path(path).stem, "path": path, "exists": Path(path).exists()} for path in store.get("desktopFiles", {})]
    return {"ok": True, "theme": base, "fallbacks": fallbacks, "themes": available, "backupThemes": themes(True), "icons": mapping, "applications": app_list, "aliases": aliases, "overrides": store.get("overrides", {}), "paths": paths, "colorPaths": color_paths()}


def apply(payload):
    store = read_store()
    theme = payload.get("theme", store.get("theme"))
    if theme not in {t["id"] for t in themes()}:
        raise ValueError("Choose an installed icon theme.")
    fallbacks = fallback_themes(payload.get("fallbacks", store.get("fallbacks", [])), theme, {t["id"] for t in themes(True)})
    overrides = dict(store.get("overrides", {}))
    old_files = {Path(value["path"]) for value in overrides.values()}
    app_id = payload.get("application")
    updates = {}
    if app_id:
        app = next((a for a in applications() if a["id"] == app_id), None)
        if not app:
            raise ValueError("Application is no longer installed.")
        original = app["icon"]
        if payload.get("reset"):
            overrides.pop(app_id, None)
        else:
            source = payload.get("source", "")
            if not isinstance(source, str) or not source:
                raise ValueError("Choose an icon name or a PNG/SVG file.")
            if source.startswith("/"):
                path = Path(source)
            else:
                from urllib.parse import unquote, urlparse
                url = icon_map(theme, fallbacks).get(source)
                if not url:
                    raise ValueError("Icon name was not found in the selected theme.")
                path = Path(unquote(urlparse(url).path))
            if path.suffix.lower() not in EXTENSIONS or not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
                raise ValueError("Choose a local PNG, SVG or XPM smaller than 8 MB.")
            import hashlib
            # A stable managed filename also supports desktop entries with absolute Icon paths.
            filename = "ai-" + hashlib.sha256(app_id.encode() + path.read_bytes()).hexdigest()[:24] + path.suffix.lower()
            destination = ROOT / "scalable/apps" / filename
            updates[destination] = path.read_bytes()
            overrides[app_id] = {"path": str(destination), "original": original, "source": source}
    inheritance = ",".join(dict.fromkeys([theme, *fallbacks, "hicolor"]))
    updates[ROOT / "index.theme"] = f"[Icon Theme]\nName=Artificial Impulse\nComment=Personal icon overrides\nInherits={inheritance}\nDirectories=scalable/apps\n\n[scalable/apps]\nSize=48\nType=Scalable\nMinSize=8\nMaxSize=512\nContext=Applications\n"
    desktop_overrides = {}
    for app in applications():
        if app["id"] in overrides:
            local = DATA / "applications" / app["id"]
            previous = store.get("desktopFiles", {}).get(str(local))
            desktop_overrides[str(local)] = previous if previous is not None else {"existed": local.exists(), "content": local.read_text() if local.exists() else None}
            updates[local] = edit_ini(Path(app["file"]).read_text(), "Desktop Entry", "Icon", overrides[app["id"]]["path"])
            desktop_overrides[str(local)] = dict(desktop_overrides[str(local)], generated=updates[local])
    # Restore local desktop entries when their per-application override is removed.
    restores = {Path(p): meta for p, meta in store.get("desktopFiles", {}).items() if p not in desktop_overrides}
    for name, path, section, key in targets():
        updates[path] = edit_ini(path.read_text() if path.exists() else "", section, key, OVERLAY)
    for _, path, key, separator in legacy_targets():
        updates[path] = edit_property(path.read_text(), key, separator)
    next_store = {"theme": theme, "fallbacks": fallbacks, "overrides": overrides, "desktopFiles": desktop_overrides}
    updates[STORE] = json.dumps(next_store, indent=2) + "\n"
    backup = STATE / "artificial-impulse/icon-backups" / (time.strftime("%Y%m%d-%H%M%S") + "-" + str(time.time_ns()))
    backup.mkdir(parents=True)
    previous = {path: path.read_bytes() if path.exists() else None for path in {*updates, *restores, *old_files}}
    manifest = {}
    for index, (path, content) in enumerate(previous.items()):
        manifest[str(path)] = str(index) if content is not None else None
        if content is not None:
            (backup / str(index)).write_bytes(content)
    (backup / "manifest.json").write_text(json.dumps(manifest, indent=2))
    try:
        # Kirigami requires declared directories even when there are no custom images.
        ROOT.joinpath("scalable/apps").mkdir(parents=True, exist_ok=True)
        for path, content in updates.items():
            atomic(path, content)
        for path, meta in restores.items():
            current = path.read_text() if path.exists() else ""
            if not meta["existed"] and current == meta.get("generated"):
                path.unlink(missing_ok=True)
            else:
                original = next((value["original"] for identity, value in store["overrides"].items()
                                 if DATA / "applications" / identity == path), None)
                if original is not None:
                    atomic(path, edit_ini(current, "Desktop Entry", "Icon", original))
        # Remove stale generated aliases/images, including a changed extension.
        keep = {p.name for p in updates if p.parent == ROOT / "scalable/apps"} | {Path(o["path"]).name for o in overrides.values()}
        for path in old_files:
            if path.parent == ROOT / "scalable/apps" and path.name not in keep:
                path.unlink(missing_ok=True)
    except Exception:
        for path, content in previous.items():
            if content is None:
                path.unlink(missing_ok=True)
            else:
                atomic(path, content)
        raise
    warnings = []
    if (CONFIG / "xsettingsd/xsettingsd.conf").exists() and shutil.which("pkill"):
        try:
            subprocess.run(["pkill", "-HUP", "-u", str(os.getuid()), "-x", "xsettingsd"], capture_output=True, timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            warnings.append("XSettings may need to be reloaded.")
    if shutil.which("gsettings"):
        try:
            result = subprocess.run(["gsettings", "set", "org.gnome.desktop.interface", "icon-theme", OVERLAY], capture_output=True, text=True, timeout=5)
            if result.returncode:
                warnings.append("GNOME/GSettings could not be updated.")
        except (OSError, subprocess.TimeoutExpired):
            warnings.append("GNOME/GSettings could not be updated.")
    else:
        warnings.append("GSettings is unavailable.")
    result = snapshot()
    result.update(message="Icons applied. Some open applications may need reopening.", warnings=warnings, backup=str(backup))
    return result


def main():
    try:
        action = sys.argv[1] if len(sys.argv) > 1 else "snapshot"
        if action == "snapshot":
            result = snapshot()
        elif action == "preview":
            payload = json.load(sys.stdin)
            theme = payload.get("theme")
            if theme not in {t["id"] for t in themes()}:
                raise ValueError("Choose an installed icon theme.")
            fallbacks = fallback_themes(payload.get("fallbacks", []), theme, {t["id"] for t in themes(True)})
            mapping = icon_map(theme, fallbacks)
            result = {"ok": True, "previewTheme": theme, "previewKey": json.dumps([theme, fallbacks], separators=(",", ":"), ensure_ascii=False), "previewIcons": {name: mapping.get(name, "") for name in ("folder", "applications-system", "network-wireless", "user-trash")}}
        elif action == "apply":
            STATE.joinpath("artificial-impulse").mkdir(parents=True, exist_ok=True)
            with (STATE / "artificial-impulse/icons.lock").open("w") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                result = apply(json.load(sys.stdin))
        else:
            raise ValueError("Unknown icon operation.")
    except Exception as error:
        result = {"ok": False, "error": str(error)}
    print(json.dumps(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
