#!/usr/bin/env python3
"""Inventory and paged UI adapter for endless-storage. No Python tree scanner.

Each cached native process owns one immutable snapshot. At most three completed
snapshots plus one replacement coexist; exactly one process scans at a time.
No filename database, exported tree or ncdu compatibility path exists.
"""
import argparse
from collections import OrderedDict
import importlib.util
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading

_spec = importlib.util.spec_from_file_location('_storage_inventory', Path(__file__).with_name('inventory.py'))
_inventory = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_inventory)
# Public inventory helpers retained for fixture injection and metadata tests.
mounts = _inventory.mounts
discover = _inventory.discover
inventory = _inventory.inventory
volume_capacities = _inventory.volume_capacities
capacity = _inventory.capacity
authorize = _inventory.authorize
open_directory = _inventory.open_directory
inside = _inventory.inside
RESULT_STATES = ('complete', 'complete-with-warnings')
PAGE_SIZE = 60


def native_executable():
    """Explicit override, bundled binary, source checkout, then installed PATH."""
    explicit = os.environ.get('DOTS_STORAGE_EXECUTABLE')
    if explicit:
        return explicit if os.path.isfile(explicit) and os.access(explicit, os.X_OK) else None
    shell = Path(__file__).resolve().parents[2]
    candidates = [shell / 'runtime/storage/endless-storage']
    for parent in shell.parents:
        if (parent / 'runtime/storage/Cargo.toml').is_file():
            candidates.append(parent / 'runtime/storage/target/release/endless-storage')
            break
    candidates.append(Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'dots-hyperland/storage/endless-storage')
    for path in candidates:
        if path.is_file() and os.access(path, os.X_OK): return str(path)
    return shutil.which('endless-storage')


def backend_info():
    binary = native_executable()
    return dict(available=bool(binary), error='' if binary else 'native-engine-required',
                version='endless-storage · protocol 1', engine='rust')


class Native:
    """Bounded frames, concurrent response/event drain, opaque native scan IDs."""
    def __init__(self, executable):
        self.proc = subprocess.Popen([executable], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL)
        self.events = queue.Queue(maxsize=16)
        self.pending = {}
        self.lock = threading.Lock()
        self.serial = 0
        self.closed = False
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            while True:
                line = self.proc.stdout.readline(262146)
                if not line: break
                if len(line) > 262145 or not line.endswith(b'\n'): break
                frame = json.loads(line)
                if frame.get('protocol') != 1: break
                if frame.get('type') == 'response':
                    with self.lock:
                        reply = self.pending.get(frame.get('id'))
                        if reply: reply.put_nowait(frame)
                elif frame.get('type') == 'event':
                    # At 4 events/s the scan consumer continuously drains this
                    # bounded queue. Backpressure never accumulates a tree.
                    self.events.put(frame)
        except (OSError, ValueError, queue.Full):
            pass
        finally:
            with self.lock:
                self.closed = True
                for reply in self.pending.values():
                    if reply.empty(): reply.put_nowait(dict(ok=False, error=dict(code='native-engine-stopped')))
            self.events.put(dict(event='engine-exited'))

    def request(self, action, timeout=30, **fields):
        with self.lock:
            if self.closed: raise ValueError('native-engine-stopped')
            self.serial += 1
            identity = str(self.serial)
            reply = queue.Queue(maxsize=1)
            self.pending[identity] = reply
            try:
                self.proc.stdin.write(json.dumps(dict(id=identity, action=action, **fields), ensure_ascii=True).encode() + b'\n')
                self.proc.stdin.flush()
            except OSError:
                self.pending.pop(identity, None)
                raise ValueError('native-engine-stopped') from None
        try:
            frame = reply.get(timeout=timeout)
            if not frame.get('ok'): raise ValueError(frame.get('error', {}).get('code', 'native-protocol-error'))
            return frame['data']
        except queue.Empty:
            raise ValueError('native-engine-unresponsive') from None
        finally:
            with self.lock: self.pending.pop(identity, None)

    def close(self):
        try:
            if self.proc.poll() is None:
                self.proc.stdin.close()  # EOF closes dispatcher even during a blocked syscall.
                try: self.proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    self.proc.wait(timeout=1)
        except (OSError, ValueError): pass
        self.reader.join(timeout=1)
        self.proc.stdout.close()


class Snapshot:
    def __init__(self, native, root, volume, mount_key):
        self.native, self.root, self.volume, self.mount_key = native, root, volume, mount_key
        self.scan_id = ''
        self.summary = None

    def complete_summary(self, state, data):
        # Optimized v1 distinguishes observations from omitted coverage. Refuse
        # an older binary instead of calling every historical issue unreadable.
        required = ('unreadable_count', 'unstable_entries', 'coverage_incomplete',
                    'coverage_uncertain', 'changes_observed', 'uncertain_directories', 'issue_codes', 'execution')
        if any(key not in data for key in required): raise ValueError('native-engine-upgrade-required')
        return dict(state='complete-with-warnings' if state == 'finished-with-warnings' else 'complete',
                    engineState=state, protocol=1, scanId=self.scan_id, root=self.root,
                    bytes=data['total_bytes'], issueCount=data['issue_count'],
                    errors=data['unreadable_count'], unreadableCount=data['unreadable_count'],
                    unstableEntries=data['unstable_entries'], changesObserved=data['changes_observed'],
                    uncertainDirectories=data['uncertain_directories'], coverageIncomplete=data['coverage_incomplete'],
                    coverageUncertain=data['coverage_uncertain'], issueCodes=data['issue_codes'], execution=data['execution'],
                    skipped=data['excluded_count'], excludedCount=data['excluded_count'],
                    retainedDirectories=data['directories_retained'], elapsed=data['elapsed_ms'] / 1000,
                    identity=data['identity'])

    @staticmethod
    def coverage(node):
        return dict(issueCount=node['subtree_issue_count'], unreadableCount=node['subtree_unreadable_count'],
                    readErrors=node['subtree_unreadable_count'], unstableEntries=node['subtree_unstable_entries'],
                    changesObserved=node['changes_observed'], coverageIncomplete=node['coverage_incomplete'],
                    coverageUncertain=node['coverage_uncertain'],
                    partial=node['coverage_incomplete'] or node['coverage_uncertain'] or bool(node['exclusion']))

    def browse(self, request):
        fields = dict(scan_id=self.scan_id, offset=max(0, int(request.get('offset', 0))),
                      limit=PAGE_SIZE, sort='name' if request.get('order') == 'name' else 'size_desc',
                      directories_only=True, query=str(request.get('query', ''))[:2048],
                      others=bool(request.get('others')), chart_width=max(240, min(4000, int(request.get('width', 800)))))
        if request.get('nodeId') is not None:
            fields['node_id'] = int(request['nodeId'])
        else:
            path = request.get('path', self.root)
            if not inside(path, self.root): raise ValueError('outside-volume')
            fields['path_hex'] = os.fsencode(os.path.relpath(path, self.root) if path != self.root else '').hex()
        try:
            data = self.native.request('browse', **fields)
        except ValueError as error:
            if str(error) != 'response_too_large': raise
            # Pathological names still retain all native data. Reduce this page,
            # never truncate totals or silently drop a directory.
            fields['limit'] = 1
            data = self.native.request('browse', **fields)
        node = data['node']
        display_path = os.path.join(self.root, data['path']) if data['path'] else self.root
        raw_prefix = os.fsencode(self.root).rstrip(b'/') + b'/'
        if data['path_hex']: raw_prefix += bytes.fromhex(data['path_hex']) + b'/'
        def row(child):
            return dict(nodeId=child['node_id'], key=(raw_prefix + bytes.fromhex(child['name_hex'])).hex(), name=child['name'],
                        path=os.path.join(display_path, child['name']), bytes=child['allocated_bytes'],
                        directory=True, **self.coverage(child),
                        excluded=child['exclusion'] or '', issues=child['issues'])
        segments = [dict(row(c), kind='folder') if c['type'] == 'directory' else
                    dict(kind='others', name='Other folders', bytes=c['allocated_bytes'], count=c['count'], path='')
                    for c in data['segments']]
        if node['direct_files_bytes']:
            segments.append(dict(kind='files', name='Direct entries', bytes=node['direct_files_bytes'], path=''))
        if node['own_bytes']:
            segments.append(dict(kind='metadata', name='Directory metadata', bytes=node['own_bytes'], path=''))
        breadcrumbs, prefix = [], self.root
        for crumb in data['breadcrumbs']:
            if crumb['node_id'] != 0: prefix = os.path.join(prefix, crumb['name'])
            breadcrumbs.append(dict(name=crumb['name'], nodeId=crumb['node_id'], path=prefix))
        return dict(nodeId=node['node_id'], scanId=self.scan_id, path=display_path, root=self.root,
                    state=self.summary['state'], bytes=node['allocated_bytes'], **self.coverage(node), issues=node['issues'],
                    issueSamplesTruncated=node['issue_samples_truncated'], excludedEntries=node['excluded_entries'],
                    excluded=[], segments=segments, breadcrumbs=breadcrumbs, chartWidth=data['chart_width'],
                    files=node['direct_entries'], fileBytes=node['direct_files_bytes'], ownBytes=node['own_bytes'],
                    rows=[row(c) for c in data['children'] if c['type'] == 'directory'],
                    offset=data['offset'], count=data['total_children'], totalCount=data['directory_count'],
                    pageSize=data['limit'], nextOffset=data['next_offset'], more=data['next_offset'] is not None)


class Worker:
    def __init__(self, emit):
        self.emit = emit
        self.cache = OrderedDict()
        self.thread = None
        self.active = None
        self.lock = threading.RLock()
        self.cancelled = threading.Event()
        self.closing = False

    @staticmethod
    def mount_key_for(path, volume):
        _, current = authorize(path, volume, mounts())
        return (current.get('mountId'), current.get('root'), current.get('source'))

    def dispatch(self, request):
        identity = request.get('id')
        def reply(**fields): self.emit(dict(id=identity, **fields))
        action = request.get('action')
        try:
            if action == 'inventory':
                reply(event='inventory', **discover(), backend=backend_info())
            elif action == 'cancel':
                self.cancelled.set()
                with self.lock: active = self.active
                if active and active.scan_id:
                    active.native.request('cancel', timeout=2, scan_id=active.scan_id)
            elif action in ('open', 'browse'):
                volume, path = request['volume'], request.get('path', '')
                with self.lock:
                    snapshot = next((s for s in reversed(self.cache.values()) if s.volume == volume and
                                    (s.scan_id == request.get('snapshot') if request.get('snapshot') else inside(path, s.root))), None)
                    reset = False
                    if not snapshot and request.get('scopeRoot'):
                        # A stale presentation ID must not force a scan when a
                        # newer snapshot of this exact scope already exists.
                        snapshot = next((s for s in reversed(self.cache.values()) if s.volume == volume and
                                         s.root == request['scopeRoot']), None)
                        if snapshot:
                            request = dict(request, nodeId=0, offset=0, query='', others=False)
                            reset = True  # Old node IDs never cross generations.
                    if not snapshot:
                        reply(event='cache-miss', path=path)
                        return
                    if snapshot.native.closed or snapshot.native.proc.poll() is not None:
                        self.discard(snapshot)
                        reply(event='cache-miss', path=path)
                        return
                    if self.mount_key_for(snapshot.root, volume) != snapshot.mount_key:
                        self.discard(snapshot)
                        raise ValueError('volume-disconnected')
                    # Do not retire a snapshot while a page from it is being
                    # answered. Its reply precedes a replacement's publication.
                    view = snapshot.browse(request)
                    self.cache.move_to_end(snapshot.scan_id)
                    reply(event='view', volume=volume, summary=snapshot.summary, view=view, viewReset=reset)
            elif action == 'scan':
                if self.thread and self.thread.is_alive(): raise ValueError('scan-already-running')
                workers = request.get('workers', 0)
                if type(workers) is not int or workers not in range(5): raise ValueError('invalid_workers')
                binary = native_executable()
                if not binary: raise ValueError('native-engine-required')
                volume = request['volume']
                path, _ = authorize(request['path'], volume, mounts())
                key = self.mount_key_for(path, volume)
                self.cancelled = threading.Event()
                self.thread = threading.Thread(target=self.scan, args=(request, path, volume, key, binary, reply), daemon=True)
                self.thread.start()
            else: raise ValueError('unknown-action')
        except (OSError, ValueError, KeyError, TypeError) as error:
            reply(event='error', error=str(error) if isinstance(error, ValueError) else 'native-protocol-error')

    def scan(self, request, path, volume, key, binary, reply):
        snapshot = None
        retained = False
        try:
            snapshot = Snapshot(Native(binary), path, volume, key)
            with self.lock: self.active = snapshot
            options = dict(root_hex=os.fsencode(path).hex())
            if request.get('workers'): options['workers'] = request['workers']
            ack = snapshot.native.request('scan', timeout=5, **options)
            snapshot.scan_id = ack['scan_id']
            if self.cancelled.is_set(): snapshot.native.request('cancel', scan_id=snapshot.scan_id)
            while True:
                frame = snapshot.native.events.get()
                if frame.get('event') == 'engine-exited': raise ValueError('native-engine-stopped')
                if frame.get('scan_id') != snapshot.scan_id: continue
                data = frame['data']
                if frame['event'] == 'progress':
                    progress = data['progress']
                    reply(event='progress', directories=progress['directories_seen'],
                          entries=progress['directories_seen'] + progress['files_seen'],
                          bytes=progress['allocated_bytes_processed'], elapsed=data['elapsed_ms'] / 1000,
                          nativeScanId=snapshot.scan_id)
                elif frame['event'] == 'completed':
                    if self.cancelled.is_set() or frame['state'] == 'aborted':
                        reply(event='analysis-failed', volume=volume, state='cancelled', error='cancelled')
                        return
                    if frame['state'] not in ('finished', 'finished-with-warnings'):
                        reply(event='analysis-failed', volume=volume, state='error',
                              error=data.get('error', {}).get('code', 'native-scan-failed'), diagnostic=data)
                        return
                    if self.mount_key_for(path, volume) != key: raise ValueError('volume-disconnected')
                    snapshot.summary = snapshot.complete_summary(frame['state'], data)
                    view = snapshot.browse(dict(path=path, width=request.get('width', 800)))
                    if self.cancelled.is_set():
                        reply(event='analysis-failed', volume=volume, state='cancelled', error='cancelled')
                        return
                    with self.lock:
                        # One snapshot per exact scope; previous valid result is
                        # released only AFTER its successful replacement exists.
                        old = [s for s in self.cache.values() if s.root == path and s.volume == volume]
                        for s in old: self.discard(s)
                        self.cache[snapshot.scan_id] = snapshot
                        while len(self.cache) > 3:
                            _, evicted = self.cache.popitem(last=False)
                            evicted.native.close()
                        retained = True
                    if not self.closing: reply(event='complete', volume=volume, summary=snapshot.summary, view=view)
                    return
        except (OSError, ValueError, KeyError, TypeError):
            error = sys.exc_info()[1]
            if not self.closing: reply(event='error', error=str(error) if isinstance(error, ValueError) else 'native-protocol-error')
        finally:
            if snapshot and not retained: snapshot.native.close()
            with self.lock: self.active = None

    def discard(self, snapshot):
        with self.lock: self.cache.pop(snapshot.scan_id, None)
        snapshot.native.close()

    def close(self):
        self.closing = True
        self.cancelled.set()
        with self.lock:
            active = self.active
            snapshots = list(self.cache.values())
            self.cache.clear()
        if active: active.native.close()
        if self.thread: self.thread.join(timeout=2)
        for snapshot in snapshots: snapshot.native.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', action='store_true')
    args = parser.parse_args()
    output_lock = threading.Lock()
    def emit(frame):
        with output_lock:
            print(json.dumps(frame, ensure_ascii=True, separators=(',', ':')), flush=True)
    worker = Worker(emit)
    try:
        if args.inventory: emit(dict(event='inventory', **discover(), backend=backend_info())); return
        emit(dict(event='ready'))
        for line in sys.stdin:
            if len(line) > 65536: emit(dict(event='error', error='invalid-request')); continue
            try:
                request = json.loads(line)
                if not isinstance(request, dict): raise ValueError()
            except ValueError:
                emit(dict(event='error', error='invalid-request'))
                continue
            worker.dispatch(request)
    except (BrokenPipeError, KeyboardInterrupt): pass
    finally: worker.close()


if __name__ == '__main__': main()
