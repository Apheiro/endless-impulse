"""Host authentication must fail closed and keep credentials out of argv."""
import ctypes as C
import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("lock_auth", ROOT / "src/quickshell/scripts/lock/authenticate.py")
auth = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(auth)


class LockAuthenticationTests(unittest.TestCase):
    def test_only_pam_success_unlocks(self):
        for status, expected in ((0, 0), (7, 1), (11, 1), (4, 2), (19, 2)):
            with self.subTest(status=status):
                pam = MagicMock()
                pam.pam_start.return_value = 0
                pam.pam_authenticate.return_value = status
                with patch.object(auth.C, "CDLL", return_value=pam):
                    self.assertEqual(auth.authenticate("example"), expected)
                self.assertEqual(pam.pam_start.call_args.args[0], b"login")
                pam.pam_end.assert_called_once()

    def test_start_failure_never_authenticates(self):
        pam = MagicMock()
        pam.pam_start.return_value = 4
        with patch.object(auth.C, "CDLL", return_value=pam):
            self.assertEqual(auth.authenticate("example"), 2)
        pam.pam_authenticate.assert_not_called()

    def test_invalid_input_fails_without_pam_attempt(self):
        for value in (None, {}, 12, "bad\0password"):
            with patch.object(auth.C, "CDLL") as load:
                self.assertEqual(auth.authenticate(value), 2)
                load.assert_not_called()

    def test_malformed_protocol_and_missing_library_fail_closed(self):
        for data in ("", "not json", '"example"\n'):
            with patch.object(auth.sys, "stdin", io.StringIO(data)), \
                    patch.object(auth.C, "CDLL", side_effect=OSError):
                self.assertEqual(auth.main(), 2)

    def test_conversation_answers_username_and_password_separately(self):
        libc = C.CDLL(None)
        callback = auth.conversation(b"example", b"test-user", libc)
        messages = [auth.Message(style, b"prompt") for style in (2, 1, 4)]
        pointers = (C.POINTER(auth.Message) * 3)(*[C.pointer(message) for message in messages])
        replies = C.POINTER(auth.Response)()
        self.assertEqual(callback(3, pointers, C.byref(replies), None), 0)
        try:
            self.assertEqual(C.string_at(replies[0].text), b"test-user")
            self.assertEqual(C.string_at(replies[1].text), b"example")
            self.assertIsNone(replies[2].text)
        finally:
            for reply in replies[:3]:
                if reply.text:
                    libc.free(reply.text)
            libc.free(replies)

    def test_conversation_rejects_unknown_prompts(self):
        libc = C.CDLL(None)
        callback = auth.conversation(b"example", b"user", libc)
        message = auth.Message(99, b"unexpected")
        pointers = (C.POINTER(auth.Message) * 1)(C.pointer(message))
        replies = C.POINTER(auth.Response)()
        self.assertEqual(callback(1, pointers, C.byref(replies), None), 19)
        self.assertFalse(replies)

    def test_host_process_has_private_input_and_clean_library_environment(self):
        qml = (ROOT / "src/quickshell/modules/shared/panels/lock/LockContext.qml").read_text()
        self.assertIn('write(payload)', qml)
        self.assertIn('"LD_LIBRARY_PATH": ""', qml)
        self.assertIn('exitCode === 0 && exitStatus === 0', qml)
        self.assertIn('passwordClearTimer.stop()', qml)
        self.assertIn('if (root.unlockInProgress) return', qml)
        command = next(line for line in qml.splitlines() if 'command: [root.hostPamPython' in line)
        self.assertNotIn('currentText', command)


if __name__ == "__main__":
    unittest.main()
