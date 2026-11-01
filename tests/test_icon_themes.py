"""Icon integration against disposable XDG roots; never changes session settings."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "src/quickshell/scripts/icons/themes.py"


class IconThemeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.env = patch.dict(os.environ, {"HOME": str(self.base), "XDG_CONFIG_HOME": str(self.base / "config"), "XDG_DATA_HOME": str(self.base / "data"), "XDG_STATE_HOME": str(self.base / "state"), "XDG_DATA_DIRS": str(self.base / "share")})
        self.env.start()
        self.addCleanup(self.env.stop)
        spec = importlib.util.spec_from_file_location("icon_themes", SCRIPT)
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.tools = patch.object(self.m.shutil, "which", return_value=None)
        self.tools.start()
        self.addCleanup(self.tools.stop)
        self.theme("Base", inherits="Other")
        self.theme("Other", inherits="Base")
        self.write(self.m.DATA / "icons/Base/48x48/apps/folder.svg", '<svg xmlns="http://www.w3.org/2000/svg"/>')
        self.write(self.m.DATA / "icons/Other/48x48/apps/inherited.png", b"image")
        self.write(self.m.DATA / "icons/hicolor/48x48/apps/webapp.png", b"fallback")
        self.write(self.m.DATA / "applications/demo.desktop", "[Desktop Entry]\nType=Application\nName=Demo\nIcon=webapp\nExec=demo --flag\n")
        self.write(self.m.CONFIG / "kdeglobals", "# personal\n[Icons]\nTheme=Base\n[Other]\nTheme=unchanged\n")

    def write(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text if isinstance(text, bytes) else text.encode())

    def theme(self, name, inherits=""):
        self.write(self.m.DATA / "icons" / name / "index.theme", f"[Icon Theme]\nName={name}\nDirectories=48x48/apps\nInherits={inherits}\n[48x48/apps]\nSize=48\nType=Fixed\n")

    def test_snapshot_reads_theme_inheritance_and_local_hicolor_without_writes(self):
        result = self.m.snapshot()
        self.assertEqual(result["theme"], "Base")
        self.assertTrue(result["icons"]["folder"].endswith("folder.svg"))
        self.assertIn("inherited", result["icons"])
        self.assertIn("webapp", result["icons"])
        self.assertFalse(self.m.STORE.exists())
        self.assertFalse(self.m.ROOT.exists())

    def test_apply_preserves_unrelated_keys_comments_symlinks_and_backups(self):
        gtk = self.m.CONFIG / "gtk-3.0/settings.ini"
        real = self.base / "personal-gtk.ini"
        self.write(real, "# mine\n[Settings]\ngtk-font-name=Sans 12\ngtk-icon-theme-name=Old\n")
        gtk.parent.mkdir(parents=True)
        gtk.symlink_to(real)
        result = self.m.apply({"theme": "Base"})
        self.assertTrue(gtk.is_symlink())
        self.assertIn("# mine", real.read_text())
        self.assertIn("gtk-font-name=Sans 12", real.read_text())
        self.assertIn("gtk-icon-theme-name=ArtificialImpulse", real.read_text())
        self.assertIn("[Other]\nTheme=unchanged", (self.m.CONFIG / "kdeglobals").read_text())
        self.assertTrue(Path(result["backup"], "manifest.json").exists())
        for row in result["paths"]:
            self.assertTrue(row["exists"])

    def test_override_copies_image_and_reset_restores_inherited_icon(self):
        source = self.base / "custom.png"
        self.write(source, b"first")
        result = self.m.apply({"theme": "Base", "application": "demo.desktop", "source": str(source)})
        first = result["overrides"]["demo.desktop"]["path"]
        self.assertEqual(Path(first).read_bytes(), b"first")
        source.unlink()
        self.assertIn("webapp", self.m.snapshot()["icons"])
        result = self.m.apply({"theme": "Base", "application": "demo.desktop", "reset": True})
        self.assertEqual(result["overrides"], {})
        self.assertTrue(result["icons"]["webapp"].endswith("hicolor/48x48/apps/webapp.png"))
        self.assertFalse(Path(first).exists())

    def test_replacement_name_and_content_revision(self):
        result = self.m.apply({"theme": "Base", "application": "demo.desktop", "source": "folder"})
        first = result["overrides"]["demo.desktop"]["path"]
        source = self.base / "second.svg"
        self.write(source, '<svg xmlns="http://www.w3.org/2000/svg"><g/></svg>')
        result = self.m.apply({"theme": "Base", "application": "demo.desktop", "source": str(source)})
        self.assertNotEqual(first, result["overrides"]["demo.desktop"]["path"])
        self.assertFalse(Path(first).exists())

    def test_absolute_desktop_icon_can_be_changed_and_reset(self):
        absolute = self.base / "original.png"
        self.write(absolute, b"original")
        desktop = self.m.DATA / "applications/demo.desktop"
        self.write(desktop, f"[Desktop Entry]\nName=Demo\nExec=demo --flag\nIcon={absolute}\n")
        original_text = desktop.read_text()
        result = self.m.apply({"theme": "Base", "application": "demo.desktop", "source": "folder"})
        self.assertNotEqual(desktop.read_text(), original_text)
        self.assertEqual(result["applications"][0]["icon"], str(absolute))
        result = self.m.apply({"theme": "Base", "application": "demo.desktop", "reset": True})
        self.assertEqual(desktop.read_text(), original_text)
        self.assertEqual(result["overrides"], {})

    def test_shared_icon_name_only_changes_selected_application(self):
        other = self.m.DATA / "applications/other.desktop"
        self.write(other, "[Desktop Entry]\nName=Other\nIcon=webapp\nExec=other\n")
        before = other.read_text()
        result = self.m.apply({"theme": "Base", "application": "demo.desktop", "source": "folder"})
        self.assertEqual(other.read_text(), before)
        self.assertNotIn("other", result["aliases"])
        self.assertIn("demo", result["aliases"])
        self.assertTrue(result["icons"]["webapp"].endswith("hicolor/48x48/apps/webapp.png"))

    def test_optional_gtk2_xsettings_and_later_desktop_edits_are_preserved(self):
        gtk = self.base / ".gtkrc-2.0"
        xs = self.m.CONFIG / "xsettingsd/xsettingsd.conf"
        self.write(gtk, '# font\ngtk-font-name="Sans 12"\ngtk-icon-theme-name="Old"\n')
        self.write(xs, 'Net/IconThemeName "Old"\nNet/ThemeName "Keep"\n')
        self.m.apply({"theme": "Base", "application": "demo.desktop", "source": "folder"})
        self.assertIn('gtk-icon-theme-name="ArtificialImpulse"', gtk.read_text())
        self.assertIn('Net/IconThemeName "ArtificialImpulse"', xs.read_text())
        self.assertIn('Net/ThemeName "Keep"', xs.read_text())
        desktop = self.m.DATA / "applications/demo.desktop"
        desktop.write_text(desktop.read_text().replace("--flag", "--new-flag"))
        self.m.apply({"theme": "Base", "application": "demo.desktop", "reset": True})
        self.assertIn("--new-flag", desktop.read_text())
        self.assertIn("Icon=webapp", desktop.read_text())

    def test_hidden_desktop_entry_masks_system_application(self):
        self.write(self.base / "share/applications/demo.desktop", "[Desktop Entry]\nName=System Demo\nIcon=folder\n")
        self.write(self.m.DATA / "applications/demo.desktop", "[Desktop Entry]\nHidden=true\n")
        self.assertEqual(self.m.applications(), [])

    def test_invalid_theme_or_icon_leaves_configuration_untouched(self):
        for payload in ({"theme": "../Base"}, {"theme": "Base", "application": "demo.desktop", "source": "missing-icon"}):
            with self.assertRaises(ValueError):
                self.m.apply(payload)
        self.assertFalse(self.m.STORE.exists())
        self.assertIn("Theme=Base", (self.m.CONFIG / "kdeglobals").read_text())

    def test_ordered_backups_preview_resolution_and_valid_empty_overlay(self):
        self.theme("BackupOne")
        self.theme("BackupTwo")
        self.write(self.m.DATA / "icons/BackupOne/48x48/apps/missing.svg", b"first backup")
        self.write(self.m.DATA / "icons/BackupTwo/48x48/apps/missing.svg", b"second backup")
        self.write(self.m.DATA / "icons/hicolor/48x48/apps/missing.svg", b"last fallback")
        result=self.m.apply({"theme":"Base", "fallbacks":["BackupTwo","BackupOne","BackupTwo","Base","hicolor"]})
        self.assertEqual(result["fallbacks"],["BackupTwo","BackupOne"])
        self.assertTrue(result["icons"]["missing"].endswith("BackupTwo/48x48/apps/missing.svg"))
        self.assertIn("Inherits=Base,BackupTwo,BackupOne,hicolor",(self.m.ROOT/"index.theme").read_text())
        self.assertTrue((self.m.ROOT/"scalable/apps").is_dir())
        self.assertTrue(self.m.icon_map("Base",["BackupOne","BackupTwo"])["missing"].endswith("BackupOne/48x48/apps/missing.svg"))
        # An application-only edit keeps the fallback order.
        result=self.m.apply({"theme":"Base", "application":"demo.desktop", "source":"missing"})
        self.assertEqual(result["fallbacks"],["BackupTwo","BackupOne"])
        self.assertEqual(Path(result["overrides"]["demo.desktop"]["path"]).read_bytes(),b"second backup")

    def test_hidden_theme_can_be_used_as_backup_without_becoming_a_primary_choice(self):
        self.theme("HiddenBackup")
        index=self.m.DATA/"icons/HiddenBackup/index.theme"
        index.write_text(index.read_text().replace("Name=HiddenBackup", "Name=HiddenBackup\nHidden=true"))
        self.assertNotIn("HiddenBackup",[theme["id"] for theme in self.m.themes()])
        self.assertIn("HiddenBackup",[theme["id"] for theme in self.m.snapshot()["backupThemes"]])
        self.assertEqual(self.m.apply({"theme":"Base","fallbacks":["HiddenBackup"]})["fallbacks"],["HiddenBackup"])

    def test_invalid_backups_do_not_write_files(self):
        for fallbacks in ("Other", ["missing"], ["../Other"], ["ArtificialImpulse"], [1]):
            with self.assertRaises(ValueError):self.m.apply({"theme":"Base","fallbacks":fallbacks})
        self.assertFalse(self.m.STORE.exists())
        self.assertFalse(self.m.ROOT.exists())

    def test_failed_write_restores_all_previous_files(self):
        before = (self.m.CONFIG / "kdeglobals").read_bytes()
        atomic = self.m.atomic
        failed = False
        def fail_once(path, content):
            nonlocal failed
            if path == self.m.CONFIG / "gtk-4.0/settings.ini" and not failed:
                failed = True
                raise OSError("write failed")
            return atomic(path, content)
        with patch.object(self.m, "atomic", side_effect=fail_once):
            with self.assertRaises(OSError):
                self.m.apply({"theme": "Base"})
        self.assertEqual(before, (self.m.CONFIG / "kdeglobals").read_bytes())
        self.assertFalse(self.m.STORE.exists())
        self.assertFalse((self.m.CONFIG / "gtk-3.0/settings.ini").exists())


if __name__ == "__main__":
    unittest.main()
