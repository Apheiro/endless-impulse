"""Smoke-test real desktop helpers against the selected Python runtime."""
from pathlib import Path
import subprocess
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "src/quickshell/scripts"


class PythonRuntimeTests(unittest.TestCase):
    def test_material_palette_generation(self):
        result = subprocess.run([sys.executable, str(SCRIPTS / "colors/generate_colors_material.py"),
                                 "--color", "#6750a4"], text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.strip())

    def test_thumbnail_runtime_loads_gnome_desktop(self):
        result = subprocess.run([sys.executable, str(SCRIPTS / "thumbnails/thumbgen.py"), "--help"],
                                text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Usage:", result.stdout)
