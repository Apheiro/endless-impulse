"""Check rebranding migrations without touching the user's preferences or keyring."""
import importlib.util
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "src/quickshell/scripts"
spec = importlib.util.spec_from_file_location("branding", SCRIPTS / "shell/branding.py")
branding = importlib.util.module_from_spec(spec)
spec.loader.exec_module(branding)


class BrandingTests(unittest.TestCase):
    def test_preferences_move_once_and_legacy_paths_keep_working(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            environment = {"HOME": directory, "XDG_CONFIG_HOME": str(base / "config"),
                           "XDG_STATE_HOME": str(base / "state")}
            for root in (base / "config", base / "state"):
                legacy = root / "illogical-impulse"
                legacy.mkdir(parents=True)
                (legacy / "preferences").write_text("keep my preferences")
            branding.migrate(environment)
            branding.migrate(environment)
            for root in (base / "config", base / "state"):
                self.assertTrue((root / "illogical-impulse").is_symlink())
                self.assertEqual((root / "endless-Impulse/preferences").read_text(), "keep my preferences")
                self.assertEqual((root / "illogical-impulse/preferences").read_text(), "keep my preferences")

    def test_custom_legacy_symlink_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            custom = base / "custom"
            custom.mkdir()
            (custom / "preferences").write_text("custom settings")
            (base / "illogical-impulse").symlink_to(custom, target_is_directory=True)
            branding.migrate_directory(base)
            self.assertTrue((base / "illogical-impulse").is_symlink())
            self.assertEqual((base / "endless-Impulse/preferences").read_text(), "custom settings")

    def test_existing_new_preferences_are_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            for name in ("illogical-impulse", "endless-Impulse"):
                (base / name).mkdir()
                (base / name / "preferences").write_text(name)
            branding.migrate_directory(base)
            for name in ("illogical-impulse", "endless-Impulse"):
                self.assertEqual((base / name / "preferences").read_text(), name)

    def test_keyring_reads_new_identity_then_falls_back_to_legacy(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            tool = base / "secret-tool"
            tool.write_text('#!/bin/sh\nif [ "$3" = "$FAKE_KEYRING_ID" ]; then printf \'%s\\n\' \'{"fixture":true}\'; else exit 1; fi\n')
            tool.chmod(0o755)
            for identity in ("endless-Impulse", "artificial-impulse", "illogical-impulse"):
                result = subprocess.run(["bash", str(SCRIPTS / "keyring/try_lookup.sh")],
                    env=dict(os.environ, PATH=str(base) + os.pathsep + os.environ["PATH"], FAKE_KEYRING_ID=identity),
                    capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), '{"fixture":true}')

    def test_intermediate_brand_migrates_config_state_and_clipboard_without_loss(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            env = {"HOME": directory, **{f"XDG_{kind}_HOME": str(base / kind)
                    for kind in ("CONFIG", "STATE", "DATA")}}
            for kind in ("CONFIG", "STATE", "DATA"):
                legacy = base / kind / "artificial-impulse"
                legacy.mkdir(parents=True)
                (legacy / "fixture").write_text("preserve")
            branding.migrate(env)
            branding.migrate(env)
            for kind in ("CONFIG", "STATE", "DATA"):
                self.assertEqual((base / kind / "endless-Impulse/fixture").read_text(), "preserve")
                self.assertEqual((base / kind / "artificial-impulse/fixture").read_text(), "preserve")

    def test_intermediate_brand_takes_precedence_without_merging_legacy_data(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            for name in ("artificial-impulse", "illogical-impulse"):
                (base / name).mkdir()
                (base / name / "fixture").write_text(name)
            branding.migrate_directory(base)
            self.assertEqual((base / "endless-Impulse/fixture").read_text(), "artificial-impulse")
            self.assertEqual((base / "illogical-impulse/fixture").read_text(), "illogical-impulse")
