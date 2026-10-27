import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("graphics", ROOT / "nix/host-graphics.py")
graphics = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(graphics)


class HostGraphicsTests(unittest.TestCase):
    def test_driver_bridge_does_not_import_host_qt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            host = root / "host"
            host.mkdir()
            (host / "libEGL_nvidia.so.0").write_text("driver")
            (host / "libnvidia-glsi.so.1").write_text("driver")
            (host / "libQt6Core.so.6").write_text("must not be imported")
            (host / "gbm").mkdir()
            (host / "gbm/nvidia-drm_gbm.so").write_text("backend")
            result = graphics.nvidia_environment({"XDG_CACHE_HOME": str(root / "cache")}, [host])
            libraries = Path(result["LD_LIBRARY_PATH"])
            self.assertTrue((libraries / "libEGL_nvidia.so.0").is_symlink())
            self.assertFalse((libraries / "libQt6Core.so.6").exists())
            self.assertNotEqual(str(libraries), str(host))
            self.assertTrue((Path(result["GBM_BACKENDS_PATH"]) / "nvidia-drm_gbm.so").exists())

    def test_missing_nvidia_library_has_clear_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(RuntimeError, "EGL library was not found"):
                graphics.nvidia_environment({}, [Path(temporary)])
