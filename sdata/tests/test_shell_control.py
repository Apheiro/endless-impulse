import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("shell_control", ROOT / "dots/.config/quickshell/ii/scripts/shell/control.py")
control = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(control)


class ShellControlTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.config = self.base / "repository with spaces"
        self.config.mkdir()
        (self.config / "shell.qml").write_text("// test configuration")
        self.executable = self.base / "qs"
        self.executable.write_text("#!/bin/sh\nexit 0\n")
        self.executable.chmod(0o755)
        env = patch.dict(os.environ, {"XDG_STATE_HOME": str(self.base / "state")})
        env.start()
        self.addCleanup(env.stop)
        control.register(str(self.config / "shell.qml"), str(self.executable))

    def test_routes_to_actual_config_not_legacy_name(self):
        self.assertEqual(control.ipc_command(["brightness", "increment"]),
                         [str(self.executable), "-p", str(self.config), "ipc", "call", "brightness", "increment"])

    def test_health_uses_existing_ping_target(self):
        with patch.object(control.subprocess, "run") as run:
            run.return_value.returncode = 0
            self.assertEqual(control.main(["health"]), 0)
            self.assertEqual(run.call_args.args[0][-2:], ["health", "ping"])
            self.assertEqual(run.call_args.kwargs["timeout"], 3)

    def test_failed_health_is_not_reported_as_alive(self):
        with patch.object(control.subprocess, "run") as run:
            run.return_value.returncode = 1
            self.assertEqual(control.main(["health"]), 1)

    def test_restart_preserves_nix_launcher_and_source(self):
        launcher = self.base / "dots-hyperland"
        launcher.write_text("test")
        context = control.read_context()
        context["launcher"] = str(launcher)
        control.context_path().write_text(json.dumps(context))
        with patch.object(control.subprocess, "run") as run:
            run.return_value.returncode = 0
            self.assertEqual(control.main(["restart"]), 0)
            self.assertEqual(run.call_args_list[0].args[0][-1], "kill")
            self.assertEqual(run.call_args.args[0], [str(launcher), "--no-duplicate", "-d"])
            self.assertEqual(run.call_args.kwargs["env"]["DOTS_SHELL_SOURCE"], str(self.config))

    def test_invalid_context_is_rejected(self):
        control.context_path().write_text('{"executable":"qs","config":"relative"}')
        with self.assertRaisesRegex(ValueError, "invalid"):
            control.ipc_command(["health", "ping"])
