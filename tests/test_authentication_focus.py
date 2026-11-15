"""Isolated session transport tests. Never contact Polkit or the compositor."""
import json
import os
from pathlib import Path
import select
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import queue
import threading
import struct
import runpy
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'src/quickshell/scripts/polkit/focus.py'


def read(process, event=None, timeout=3):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if select.select([process.stdout], [], [], max(0, end - time.monotonic()))[0]:
            line = process.stdout.readline()
            if not line: raise AssertionError(process.stderr.read().decode())
            value = json.loads(line)
            if event is None or value['event'] == event:
                return value
    raise AssertionError(f'Timed out waiting for {event}')


class AuthenticationCoreTests(unittest.TestCase):
    def test_publisher_state_machine_with_pipe_fixture(self):
        # Pipe fixtures replace the socket boundary forbidden by the sandbox.
        # Production framing, stdin, ACK barrier, lease and flock remain real.
        with tempfile.TemporaryDirectory(prefix='auth-core-') as tmp:
            def pipe():
                left, right = os.pipe()
                return os.fdopen(left, 'rb', buffering=0), os.fdopen(right, 'wb', buffering=0)
            listener, wake = pipe()
            peer_input, client = pipe()
            stream, peer_output = pipe()
            class Peer:
                def fileno(self): return peer_input.fileno()
                def settimeout(self, value): pass
                def sendall(self, value): peer_output.write(value)
                def recv(self, size): return peer_input.read(size)
                def getsockopt(self, *args): return struct.pack('3i', os.getpid(), os.getuid(), os.getgid())
                def close(self): peer_input.close();peer_output.close()
            endpoint = Peer()
            read_fd, write_fd = os.pipe()
            incoming = os.fdopen(read_fd, 'rb', buffering=0)
            outgoing = os.fdopen(write_fd, 'wb', buffering=0)
            namespace = runpy.run_path(str(SCRIPT))
            globals_ = namespace['publish'].__globals__
            events = queue.Queue()
            class Listener:
                def fileno(self): return listener.fileno()
                def bind(self, path): pass
                def listen(self): pass
                def setblocking(self, value): os.set_blocking(listener.fileno(), value)
                def accept(self): listener.read(1); return endpoint, None
                def close(self): listener.close()
            globals_['socket'] = SimpleNamespace(socket=lambda family: Listener(), AF_UNIX=socket.AF_UNIX,
                                                  SOL_SOCKET=socket.SOL_SOCKET, SO_PEERCRED=socket.SO_PEERCRED)
            globals_['sys'] = SimpleNamespace(stdin=incoming)
            globals_['emit'] = lambda event, **values: events.put(dict(event=event, **values))
            globals_['LEASE'] = 0.3
            thread = threading.Thread(target=namespace['publish'], args=(Path(tmp),), daemon=True)
            thread.start()
            try:
                self.assertEqual(events.get(timeout=2)['event'], 'owner')
                wake.write(b'x')
                self.assertFalse(json.loads(stream.readline())['active'])
                outgoing.write(b'1\n')
                state = json.loads(stream.readline())
                self.assertTrue(state['active'])
                client.write(f"0\n{state['revision']}\n".encode())
                self.assertTrue(events.get(timeout=2)['synchronized'])
                client.write(b'0\n1\n')  # cannot modify published state
                self.assertFalse(json.loads(stream.readline())['active'])
                self.assertEqual(events.get(timeout=2)['event'], 'expired')
                outgoing.write(b'1\n')
                self.assertTrue(json.loads(stream.readline())['active'])
                outgoing.close()
                thread.join(timeout=2)
                self.assertFalse(thread.is_alive())
                self.assertEqual(stream.readline(), b'')
            finally:
                outgoing.close();thread.join(timeout=2);incoming.close()
                stream.close();client.close();wake.close()


class AuthenticationTransportTests(unittest.TestCase):
    def setUp(self):
        with tempfile.TemporaryDirectory(prefix='auth-socket-probe-') as tmp:
            probe = socket.socket(socket.AF_UNIX)
            try:
                probe.bind(str(Path(tmp) / 'probe'))
            except PermissionError:
                self.skipTest('Sandbox denies Unix socket bind; run on the host or in ./dev check')
            finally:
                probe.close()

    def test_subscription_barrier_exclusive_owner_disconnect_and_recovery(self):
        with tempfile.TemporaryDirectory(prefix='auth-focus-') as tmp:
            env = dict(os.environ, XDG_RUNTIME_DIR=tmp, HYPRLAND_INSTANCE_SIGNATURE='fixture')
            processes = []
            def start(mode):
                p = subprocess.Popen([sys.executable, '-u', str(SCRIPT), mode], env=env,
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
                processes.append(p)
                return p
            try:
                subscriber = start('subscribe')
                self.assertFalse(read(subscriber)['active'])
                owner = start('publish')
                self.assertEqual(read(owner)['event'], 'owner')
                self.assertFalse(read(subscriber)['active'])
                second = start('publish')
                self.assertEqual(read(second)['event'], 'occupied')
                self.assertEqual(second.wait(timeout=2), 2)
                owner.stdin.write(b'1\n'); owner.stdin.flush()
                state = read(subscriber)
                self.assertTrue(state['active'])
                subscriber.stdin.write(f"{state['revision']}\n".encode()); subscriber.stdin.flush()
                self.assertTrue(read(owner, 'present')['synchronized'])
                # Public clients cannot mutate visibility, even with publisher-like data.
                directory = next(Path(tmp).glob('ai-auth-*'))
                client = socket.socket(socket.AF_UNIX)
                client.connect(str(directory / 'state.sock'))
                self.assertTrue(json.loads(client.recv(4096))['active'])
                client.sendall(b'0\n')
                client.close()
                owner.stdin.write(b'0\n'); owner.stdin.flush()
                self.assertFalse(read(subscriber)['active'])
                owner.stdin.write(b'1\n'); owner.stdin.flush()
                self.assertTrue(read(subscriber)['active'])
                owner.kill(); owner.wait(timeout=2)
                self.assertFalse(read(subscriber)['active'])
                replacement = start('publish')
                self.assertEqual(read(replacement)['event'], 'owner')
                self.assertFalse(read(subscriber)['active'])
                replacement.stdin.close()
                self.assertEqual(replacement.wait(timeout=2), 0)
                self.assertFalse(read(subscriber)['active'])
            finally:
                for p in processes:
                    if p.poll() is None: p.kill()
                    p.wait(timeout=2)
                    for pipe in (p.stdin, p.stdout, p.stderr):
                        if pipe and not pipe.closed: pipe.close()

    def test_lease_expiry_without_polling_or_shell_heartbeat(self):
        # Shorten only the fixture's lease; production remains 15 seconds.
        with tempfile.TemporaryDirectory(prefix='auth-lease-') as tmp:
            script = Path(tmp) / 'focus.py'
            script.write_text(SCRIPT.read_text().replace('LEASE = 15.0', 'LEASE = 0.15'))
            env = dict(os.environ, XDG_RUNTIME_DIR=tmp, HYPRLAND_INSTANCE_SIGNATURE='fixture')
            p = subprocess.Popen([sys.executable, '-u', str(script), 'publish'], env=env,
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
            try:
                read(p, 'owner')
                p.stdin.write(b'1\n'); p.stdin.flush()
                read(p, 'present')
                read(p, 'expired')
            finally:
                p.stdin.close(); p.wait(timeout=2); p.stdout.close(); p.stderr.close()


if __name__ == '__main__': unittest.main()
