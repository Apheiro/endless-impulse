#!/usr/bin/env python3
"""Session-local, read-only authentication visibility transport.

Only the owning shell's private stdin can change state. Unix peer credentials,
0700 session directory, exclusive flock and EOF/lease recovery bound its lifetime.
Clients acknowledge application of a state before the shell maps its auth panel.
No action names, prompts or responses cross this channel.
"""
import ctypes
from contextlib import ExitStack
import fcntl
import hashlib
import json
import os
from pathlib import Path
import selectors
import socket
import stat
import struct
import sys
import time

LEASE = 15.0
BARRIER = 1.0


def location():
    runtime = Path(os.environ['XDG_RUNTIME_DIR'])
    if runtime.stat().st_uid != os.getuid():
        raise PermissionError('Runtime directory belongs to another user')
    session = os.environ.get('HYPRLAND_INSTANCE_SIGNATURE') or os.environ.get('WAYLAND_DISPLAY')
    if not session:
        raise RuntimeError('A Wayland session is required')
    directory = runtime / ('ai-auth-' + hashlib.sha256(session.encode()).hexdigest()[:16])
    directory.mkdir(mode=0o700, exist_ok=True)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise PermissionError('Unsafe authentication transport directory')
    return directory


def same_user(connection):
    return struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[1] == os.getuid()


def emit(event, **values):
    print(json.dumps(dict(event=event, **values)), flush=True)


def publish(directory):
    # Cover setup failures too (bind/register may fail before the event loop).
    with ExitStack() as resources:
        return _publish(directory, resources)


def _publish(directory, resources):
    lock = resources.enter_context((directory / 'owner.lock').open('w'))
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        emit('occupied')
        return 2
    path = directory / 'state.sock'
    path.unlink(missing_ok=True)
    (directory / 'ready').unlink(missing_ok=True)
    server = socket.socket(socket.AF_UNIX)
    resources.callback(server.close)
    server.bind(str(path))
    server.listen()
    server.setblocking(False)
    selector = selectors.DefaultSelector()
    resources.callback(selector.close)
    selector.register(server, selectors.EVENT_READ)
    selector.register(sys.stdin, selectors.EVENT_READ)
    os.set_blocking(sys.stdin.fileno(), False)
    clients = {}
    acknowledgements = {}
    active, revision, deadline, pending_since = False, 0, 0.0, None
    buffer = b''

    def state(connection):
        try:
            connection.sendall((json.dumps({'active': active, 'revision': revision}) + '\n').encode())

        except OSError:
            remove(connection)

    def remove(connection):
        if connection not in clients:
            return
        clients.pop(connection, None)
        acknowledgements.pop(connection, None)
        selector.unregister(connection)
        connection.close()

    (directory / 'ready').touch()
    emit('owner')
    try:
        while True:
            now = time.monotonic()
            if active and now >= deadline:
                active = False
                revision += 1
                for connection in list(clients):
                    state(connection)
                emit('expired')
                pending_since = None
            if pending_since is not None and (all(value == revision for value in clients.values()) or now - pending_since >= BARRIER):
                emit('present', synchronized=all(value == revision for value in clients.values()))
                pending_since = None
            timeout = min(0.1 if pending_since is not None else LEASE, max(0, deadline - now)) if active else None
            for key, _ in selector.select(timeout):
                if key.fileobj is server:
                    connection, _ = server.accept()
                    connection.settimeout(0.1)
                    if not same_user(connection):
                        connection.close()
                        continue
                    clients[connection] = -1
                    acknowledgements[connection] = b''
                    selector.register(connection, selectors.EVENT_READ)
                    state(connection)
                elif key.fileobj is sys.stdin:
                    chunk = os.read(sys.stdin.fileno(), 4096)
                    if not chunk:
                        return 0
                    buffer += chunk
                    while b'\n' in buffer:
                        line, buffer = buffer.split(b'\n', 1)
                        if line not in (b'0', b'1'):
                            continue
                        value = line == b'1'
                        deadline = time.monotonic() + LEASE
                        if value == active and active:
                            for connection in list(clients):
                                state(connection)
                        if value != active:
                            active = value
                            revision += 1
                            for connection in list(clients):
                                state(connection)
                            pending_since = time.monotonic() if active else None
                else:
                    connection = key.fileobj
                    try:
                        data = connection.recv(128)
                        if not data:
                            remove(connection)
                        else:
                            acknowledgements[connection] += data
                            if len(acknowledgements[connection]) > 1024:
                                remove(connection)
                                continue
                            while b'\n' in acknowledgements[connection]:
                                line, acknowledgements[connection] = acknowledgements[connection].split(b'\n', 1)
                                if line == str(revision).encode():
                                    clients[connection] = revision
                    except OSError:
                        remove(connection)
    finally:
        for connection in list(clients):
            remove(connection)
        path.unlink(missing_ok=True)


def subscribe(directory):
    # inotify watches ownership changes without an idle reconnect polling loop.
    libc = ctypes.CDLL(None, use_errno=True)
    watch = libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
    if watch < 0 or libc.inotify_add_watch(watch, os.fsencode(directory), 0x100 | 0x200) < 0:
        raise OSError(ctypes.get_errno(), 'inotify setup failed')
    selector = selectors.DefaultSelector()
    selector.register(watch, selectors.EVENT_READ)
    selector.register(sys.stdin, selectors.EVENT_READ)
    os.set_blocking(sys.stdin.fileno(), False)
    connection = None
    incoming = b''
    acknowledgement = b''
    expires = None

    def connect():
        nonlocal connection, incoming
        candidate = socket.socket(socket.AF_UNIX)
        try:
            candidate.connect(str(directory / 'state.sock'))
            if not same_user(candidate):
                raise PermissionError('Authentication publisher user mismatch')
        except OSError:
            candidate.close()
            return
        connection, incoming = candidate, b''
        selector.register(connection, selectors.EVENT_READ)

    connect()
    if connection is None:
        emit('state', active=False, revision=-1)
    while True:
        if expires is not None and time.monotonic() >= expires:
            emit('state', active=False, revision=-1)
            expires = None
        for key, _ in selector.select(None if expires is None else max(0, expires - time.monotonic())):
            if key.fileobj == watch:
                os.read(watch, 65536)
                if connection is None:
                    connect()
            elif key.fileobj is sys.stdin:
                data = os.read(sys.stdin.fileno(), 4096)
                if not data:
                    return 0
                acknowledgement += data
                while b'\n' in acknowledgement:
                    line, acknowledgement = acknowledgement.split(b'\n', 1)
                    if connection and line.isdigit():
                        try:
                            connection.sendall(line + b'\n')
                        except OSError:
                            pass
            else:
                data = connection.recv(4096)
                if not data:
                    selector.unregister(connection)
                    connection.close()
                    connection = None
                    emit('state', active=False, revision=-1)
                    connect()
                    continue
                incoming += data
                while b'\n' in incoming:
                    line, incoming = incoming.split(b'\n', 1)
                    value = json.loads(line)
                    expires = time.monotonic() + LEASE if value['active'] else None
                    emit('state', active=value['active'], revision=value['revision'])


if __name__ == '__main__':
    try:
        sys.exit({'publish': publish, 'subscribe': subscribe}[sys.argv[1]](location()))
    except (OSError, RuntimeError, KeyError) as error:
        print(f'Authentication focus transport: {error}', file=sys.stderr)
        sys.exit(1)
