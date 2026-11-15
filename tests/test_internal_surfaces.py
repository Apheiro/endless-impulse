"""Exercise real policy/reconciliation with simulated Hyprland; no live IPC."""
import copy
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/quickshell"
spec = importlib.util.spec_from_file_location("internal_surfaces", SOURCE / "scripts/hyprland/internal_surfaces.py")
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


def surface(address="0x1", cls="xembedsniproxy", title="", pid=42, **changes):
    result = dict(address=address, pid=pid, stableId=address, initialTitle=title, title=title,
                  **{"class": cls}, floating=True, xwayland=True, mapped=True, pinned=False,
                  grouped=[], fullscreen=0, fullscreenClient=0, workspace=dict(id=2, name="2"),
                  at=[20, 30], size=[32, 32])
    result.update(changes)
    return result


class PolicyTests(unittest.TestCase):
    def test_default_and_literal_anchored_rule(self):
        entries = policy.rules({})
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0]["builtin"])
        code = policy.rule_code(entries[0])
        for token in ('class="^xembedsniproxy$"', 'float=true', 'xwayland=true',
                      'workspace="special:endless-internal silent"', 'no_focus=true', 'render_unfocused=true'):
            self.assertIn(token, code)
        self.assertNotIn("artificial-minimized", code)
        self.assertNotIn("floating=", code)
        self.assertFalse(policy.matches(entries[0], surface(floating=False)))

    def test_reject_dangerous_or_duplicate_preferences_before_ipc(self):
        base = dict(windowClass="aux-tray", title="Capture holder", purpose="Legacy capture")
        bad = [dict(base, windowClass=value) for value in
               (".*", "foo|bar", 'a";os.execute()', "quickshell", "org.kde.polkit", "xembedsniproxy", "Hyprland", "desktop", "foot", "firefox", "pamac-manager")]
        bad += [dict(base, title=""), dict(base, title="Unlock authentication"),
                dict(base, purpose="\n"), dict(base, enabled="true")]
        with patch.object(policy, "ipc") as ipc:
            for entry in bad:
                with self.subTest(entry=entry), self.assertRaises(ValueError):
                    policy.reconcile(dict(rules=[entry]))
            with self.assertRaises(ValueError):
                policy.rules(dict(rules=[base, dict(base)]))
            ipc.assert_not_called()

    def test_title_is_literal_and_class_does_not_select_entire_pid(self):
        entry = policy.rules(dict(rules=[dict(windowClass="aux.capture", title='Holder [1] "capture"', purpose="Capture")]))[1]
        code = policy.rule_code(entry)
        self.assertIn(r"aux\\.capture", code)
        self.assertIn(r"\\[1\\]", code)
        self.assertNotIn("pid", code)
        self.assertFalse(policy.matches(entry, surface(cls="aux.capture", title="Main window")))
        self.assertFalse(policy.matches(entry, surface(cls="aux.capture", title=entry["title"], floating=False)))


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "state.json"
        self.clients = [surface(), surface("0x2", "editor", "Main", pid=42, floating=False)]
        self.calls = []
        self.fail_move = False
        self.ignore_move = False
        self.patcher = patch.object(policy, "ipc", side_effect=self.ipc)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def ipc(self, *args, json_result=False):
        self.calls.append(args)
        if args == ("-j", "clients"):
            return copy.deepcopy(self.clients)
        if args == ("-j", "activeworkspace"):
            return dict(id=3, name="3")
        code = args[-1]
        if "hl.dsp.window.move" in code:
            # Origin must be durably journaled before a move.
            self.assertTrue(self.path.exists())
            if self.fail_move:
                raise ValueError("simulated move failure")
            match = re.search(r'workspace="([^"]+)".*address:(0x[0-9a-f]+)', code)
            target, address = match.groups()
            if not self.ignore_move:
                client = next(c for c in self.clients if c["address"] == address)
                client["workspace"] = dict(id=-99 if target == policy.WORKSPACE else int(target), name=target)

    def test_default_moves_only_container_idempotently_then_restores(self):
        self.assertTrue(policy.reconcile({}, self.path)["ok"])
        self.assertEqual(self.clients[0]["workspace"]["name"], policy.WORKSPACE)
        self.assertEqual(self.clients[1]["workspace"]["name"], "2")
        self.assertTrue(policy.reconcile({}, self.path)["ok"])
        moves = [c for c in self.calls if "hl.dsp.window.move" in c[-1]]
        self.assertEqual(len(moves), 1)
        self.assertTrue(policy.reconcile(dict(xembedEnabled=False), self.path)["ok"])
        self.assertEqual(self.clients[0]["workspace"]["name"], "2")
        self.assertEqual(json.loads(self.path.read_text())["origins"], {})
        self.assertTrue(any("enabled=false" in c[-1] for c in self.calls))

    def test_move_failure_retains_origin_and_manual_retry_works(self):
        self.fail_move = True
        result = policy.reconcile({}, self.path)
        self.assertFalse(result["ok"])
        self.assertIn("0x1", json.loads(self.path.read_text())["origins"])
        self.fail_move = False
        self.assertTrue(policy.reconcile({}, self.path)["ok"])

    def test_silent_move_failure_is_reported(self):
        self.ignore_move = True
        self.assertFalse(policy.reconcile({}, self.path)["ok"])

    def test_restore_failure_retains_origin_for_retry(self):
        policy.reconcile({}, self.path)
        self.ignore_move = True
        self.assertFalse(policy.reconcile(dict(xembedEnabled=False), self.path)["ok"])
        self.assertIn("0x1", json.loads(self.path.read_text())["origins"])
        self.ignore_move = False
        self.assertTrue(policy.reconcile(dict(xembedEnabled=False), self.path)["ok"])
        self.assertEqual(self.clients[0]["workspace"]["name"], "2")

    def test_external_restore_does_not_move_on_disable(self):
        policy.reconcile({}, self.path)
        self.clients[0]["workspace"] = dict(id=4, name="4")
        self.calls.clear()
        policy.reconcile(dict(xembedEnabled=False), self.path)
        self.assertFalse(any("hl.dsp.window.move" in c[-1] for c in self.calls))

    def test_native_spawn_without_origin_restores_to_current_workspace(self):
        self.clients[0]["workspace"] = dict(id=-99, name=policy.WORKSPACE)
        policy.reconcile({}, self.path)
        self.assertTrue(policy.reconcile(dict(xembedEnabled=False), self.path)["ok"])
        self.assertEqual(self.clients[0]["workspace"]["name"], "3")

    def test_manual_removal_and_main_window_same_process(self):
        rule = dict(windowClass="aux-tray", title="Holder", purpose="Capture")
        self.clients = [surface(cls="aux-tray", title="Holder"), surface("0x2", "aux-tray", "Main", pid=42)]
        policy.reconcile(dict(rules=[rule]), self.path)
        self.assertEqual(self.clients[1]["workspace"]["name"], "2")
        policy.reconcile({}, self.path)
        self.assertEqual(self.clients[0]["workspace"]["name"], "2")

    def test_removed_native_rule_restore_failure_remains_recoverable(self):
        rule = dict(windowClass="aux-tray", title="Holder", purpose="Capture")
        self.clients = [surface(cls="aux-tray", title="Holder", workspace=dict(id=-99, name=policy.WORKSPACE))]
        policy.reconcile(dict(rules=[rule]), self.path)
        self.fail_move = True
        self.assertFalse(policy.reconcile({}, self.path)["ok"])
        self.assertIn("0x1", json.loads(self.path.read_text())["origins"])
        self.fail_move = False
        self.assertTrue(policy.reconcile({}, self.path)["ok"])
        self.assertEqual(self.clients[0]["workspace"]["name"], "3")

    def test_minimized_pinned_grouped_and_fullscreen_clients_are_not_moved(self):
        for changes in (dict(workspace=dict(id=-97, name="special:artificial-minimized")),
                        dict(pinned=True), dict(grouped=["0x2"]), dict(fullscreen=1)):
            self.clients = [surface(**changes)]
            self.calls.clear()
            policy.reconcile({}, self.path)
            self.assertFalse(any("hl.dsp.window.move" in c[-1] for c in self.calls))

    def test_reused_address_never_restores_old_origin(self):
        policy.reconcile({}, self.path)
        self.clients[0] = surface(pid=99, cls="editor", title="Main")
        self.calls.clear()
        policy.reconcile(dict(xembedEnabled=False), self.path)
        self.assertFalse(any("hl.dsp.window.move" in c[-1] for c in self.calls))


if __name__ == "__main__":
    unittest.main()
