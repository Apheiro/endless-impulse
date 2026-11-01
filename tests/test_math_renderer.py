"""Exercise the real renderer with all network connections disabled."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "src/quickshell/scripts/math/render-latex.mjs"


class MathRendererTests(unittest.TestCase):
    def invoke(self, expression, **options):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        output = Path(self.temp.name) / "formula.svg"
        request = dict(expression=expression, output=str(output), foreground="#abcdef", **options)
        env = dict(os.environ, NODE_OPTIONS=f"--require={ROOT / 'tests/no-network.cjs'}")
        result = subprocess.run(["node", str(RENDERER)], input=json.dumps(request),
                                text=True, capture_output=True, env=env, timeout=15)
        return result, output

    def test_fractions_roots_and_unicode_without_network(self):
        result, output = self.invoke(r"\frac{1}{x^2} + \sqrt{y} + \alpha + \sum_{i=1}^{n} i")
        self.assertEqual(result.returncode, 0, result.stderr)
        svg = ET.parse(output).getroot()
        self.assertTrue(svg.attrib["width"].endswith("px"))
        self.assertTrue(svg.attrib["height"].endswith("px"))
        self.assertIn("#abcdef", output.read_text())
        self.assertNotIn("currentColor", output.read_text())

    def test_chat_delimiters_and_matrix(self):
        result, output = self.invoke(r"$$\begin{pmatrix}1 & 2\\3 & 4\end{pmatrix}$$")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(output.exists())

    def test_invalid_expression_and_unsafe_options_fail_cleanly(self):
        for expression in ("", r"\frac{1}{"):
            with self.subTest(expression=expression):
                result, output = self.invoke(expression)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(output.exists())
        result, output = self.invoke("x", fontSize=-1)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())

    def test_external_links_are_not_emitted(self):
        result, output = self.invoke(r"\require{html}\href{https://example.com}{x}")
        if result.returncode == 0:
            self.assertNotIn('href="https:', output.read_text())
        else:
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
