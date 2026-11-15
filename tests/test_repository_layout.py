"""Guard the distinction between source paths and installed XDG paths."""
from pathlib import Path
import importlib.util
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "src/quickshell"


class RepositoryLayoutTests(unittest.TestCase):
    def test_desktop_integration_from_checkout_xdg_and_nix(self):
        layouts = {
            "checkout": ("checkout/src/quickshell", "checkout/config/xdg/config"),
            "xdg": ("custom-config/quickshell/endless-Impulse", "custom-config"),
            "nix": ("store/package/share/dots-hyperland/.config/quickshell/endless-Impulse",
                    "store/package/share/dots-hyperland/.config"),
        }
        for name, (shell_path, assets_path) in layouts.items():
            with self.subTest(layout=name), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                script = base / shell_path / "scripts/hyprland/desktop.py"
                source = base / assets_path / "hypr/hyprland/services/desktop.lua"
                script.parent.mkdir(parents=True)
                source.parent.mkdir(parents=True)
                shutil.copy2(SHELL / "scripts/hyprland/desktop.py", script)
                shutil.copy2(ROOT / "config/xdg/config/hypr/hyprland/services/desktop.lua", source)
                spec = importlib.util.spec_from_file_location("deployed_desktop", script)
                desktop = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(desktop)
                target = base / "user-config"
                main = target / "hypr/hyprland.lua"
                main.parent.mkdir(parents=True)
                original = "-- Existing user configuration\n"
                main.write_text(original)
                destination = target / "hypr/hyprland/services/desktop.lua"
                with patch.multiple(desktop, CONFIG=target, MAIN=main,
                                    PENDING=base / "state/pending.json", STATE=base / "state"), \
                        patch.object(desktop, "check_reload") as reload, \
                        patch.object(desktop, "ipc") as ipc:
                    result = desktop.install()
                    self.assertTrue(result["integrated"])
                    self.assertEqual(destination.read_text(), source.read_text())
                    self.assertTrue(main.read_text().startswith(original))
                    self.assertEqual(main.read_text().count(desktop.HOOK), 1)
                    self.assertEqual((Path(result["backup"]) / "hyprland.lua").read_text(), original)
                    self.assertTrue(desktop.install()["integrated"])
                    reload.assert_called_once_with()
                    ipc.assert_not_called()
                self.assertEqual(script.read_bytes(), (SHELL / "scripts/hyprland/desktop.py").read_bytes())

    def test_source_layers_are_present(self):
        for item in (
            "src/quickshell/shell.qml",
            "src/quickshell/settings.qml",
            "src/quickshell/services",
            "src/quickshell/modules/shared",
            "src/quickshell/modules/desktop",
            "src/quickshell/modules/windowsStyle",
            "src/quickshell/scripts",
            "config/xdg/config/hypr",
            "config/xdg/data",
            "installer/commands/install",
            "installer/distros/arch",
            "installer/dependencies/arch.json",
            "runtime/math/package-lock.json",
            "runtime/python/requirements.txt",
            "packaging/nix/package.nix",
        ):
            with self.subTest(source=item):
                self.assertTrue((ROOT / item).exists(), item)

    def test_entry_points_map_to_new_source(self):
        dev = (ROOT / "dev").read_text()
        self.assertIn('DOTS_SHELL_SOURCE="$root/src/quickshell"', dev)
        self.assertIn("unittest discover -s tests", dev)

        setup = (ROOT / "setup").read_text()
        self.assertIn("installer/lib/environment-variables.sh", setup)
        self.assertIn("SUBCMD_DIR=./installer/commands/$1", setup)
        legacy = (ROOT / "installer/commands/install/3.files-legacy.sh").read_text()
        self.assertIn('install_dir__sync src/quickshell "$XDG_CONFIG_HOME"/quickshell/endless-Impulse', legacy)
        nix = (ROOT / "packaging/nix/package.nix").read_text()
        self.assertIn("src = source + /src/quickshell;", nix)
        self.assertIn("source}/config/xdg/config/.", nix)
        variables = (ROOT / "config/xdg/config/hypr/hyprland/variables.lua").read_text()
        self.assertIn('hl.env("qsConfig", "endless-Impulse")', variables)

    def test_shapes_submodule_path_is_registered(self):
        modules = (ROOT / ".gitmodules").read_text()
        self.assertIn("path = src/quickshell/modules/shared/widgets/shapes", modules)
        self.assertTrue((SHELL / "modules/shared/widgets/shapes/ShapeCanvas.qml").is_file())


if __name__ == "__main__":
    unittest.main()
