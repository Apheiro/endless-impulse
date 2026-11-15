"""Storage never walks directories in Python; native bridge contract tests."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'src/quickshell/scripts/storage/control.py'
spec = importlib.util.spec_from_file_location('storage', SCRIPT)
storage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(storage)


class InventoryTests(unittest.TestCase):
    def test_mountinfo_aliases_subvolumes_pseudo_and_external(self):
        records = storage.mounts('''1 0 8:1 / / rw - ext4 /dev/sda1 rw
2 1 8:1 /var /alias rw - ext4 /dev/sda1 rw
3 1 0:1 / /proc rw - proc proc rw
4 1 0:2 / /run rw - tmpfs tmpfs rw
5 1 8:2 / /media/USB\\040Disk rw - exfat /dev/sdb1 rw
6 1 0:90 /@ /btrfs rw - btrfs /dev/nvme0n1p2 rw
7 1 0:90 /@home /btrfs/home rw - btrfs /dev/nvme0n1p2 rw
8 1 0:99 / /container rw - overlay overlay rw
malformed''')
        vfs = SimpleNamespace(f_blocks=100, f_bfree=40, f_bavail=30, f_frsize=4096, f_bsize=4096)
        result = storage.inventory(records, lambda _: vfs)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]['mount'], '/')
        self.assertEqual(result[0]['mounts'], ['/', '/alias'])
        self.assertTrue(any(v['mount'] == '/media/USB Disk' for v in result))
        self.assertEqual(next(v for v in result if v['fs'] == 'btrfs')['mounts'], ['/btrfs', '/btrfs/home'])

    def test_capacity_reserves_not_counted_as_used(self):
        c = storage.capacity(SimpleNamespace(f_blocks=100, f_bfree=40, f_bavail=0, f_frsize=512, f_bsize=4096))
        self.assertEqual((c['used'], c['reserved'], c['available'], c['percent']), (30720, 20480, 0, 60))
        self.assertEqual(c['total'], c['used'] + c['reserved'] + c['available'])
        self.assertTrue(c['low'])
        zero = storage.capacity(SimpleNamespace(f_blocks=0, f_bfree=0, f_bavail=-1, f_frsize=0, f_bsize=4096))
        self.assertEqual(zero['percent'], 0)

    def test_inaccessible(self):
        record = dict(device='8:1', root='/', mount='/fake', fs='ext4', source='/dev/fake')
        def denied(_): raise PermissionError()
        self.assertFalse(storage.inventory([record], denied)[0]['accessible'])

    def test_path_authorization_boundaries_and_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / 'dir').mkdir()
            (base / 'link').symlink_to(base / 'dir', target_is_directory=True)
            records = [dict(mount=tmp, device='1:2', fs='ext4')]
            self.assertEqual(storage.authorize(str(base / 'dir'), '1:2:ext4', records)[0], str(base / 'dir'))
            for path in (str(base / 'link'), str(base / '../escape'), '/root', 'relative'):
                with self.assertRaises(ValueError): storage.authorize(path, '1:2:ext4', records)
            records.append(dict(mount=str(base / 'dir'), device='2:3', fs='xfs'))
            with self.assertRaisesRegex(ValueError, 'outside-volume'):
                storage.authorize(str(base / 'dir'), '1:2:ext4', records)
            with self.assertRaises(OSError): storage.open_directory(str(base / 'link'))



class StorageAcceptanceTests(unittest.TestCase):
    def test_physical_unmounted_fuse_and_aliases(self):
        records = storage.mounts('''1 0 259:2 / / rw - ext4 /dev/nvme0n1p2 rw
2 1 259:1 / /boot rw - vfat /dev/nvme0n1p1 rw
3 1 0:71 / /home/test/ProtonDrive rw - fuse.rclone proton: rw
4 1 259:2 /home /alias rw - ext4 /dev/nvme0n1p2 rw''')
        blocks = {'blockdevices': [
            {'name': 'nvme0n1', 'type': 'disk', 'maj:min': '259:0', 'model': 'NVMe fixture', 'size': 1000000, 'rota': False, 'tran': 'nvme', 'children': [
                {'name': 'nvme0n1p2', 'type': 'part', 'maj:min': '259:2', 'size': 900000},
                {'name': 'nvme0n1p1', 'type': 'part', 'maj:min': '259:1', 'size': 100000}]},
            {'name': 'sda', 'type': 'disk', 'maj:min': '8:0', 'model': 'WD SATA fixture', 'size': 2000000, 'rota': True, 'tran': 'sata', 'children': [
                {'name': 'sda1', 'type': 'part', 'maj:min': '8:1', 'size': 2000000, 'fstype': 'ext4'}]},
            {'name': 'zram0', 'type': 'disk', 'maj:min': '253:0', 'fstype': 'swap'}]}
        vfs = SimpleNamespace(f_blocks=1000, f_bfree=400, f_bavail=300, f_frsize=1, f_bsize=1)
        result = storage.discover(records, blocks, lambda _: vfs)
        self.assertEqual(len(result['disks']), 2)
        self.assertEqual(len(result['volumes']), 4)
        sata = next(v for v in result['volumes'] if v['id'] == 'block:8:1')
        self.assertFalse(sata['mounted'])
        self.assertEqual(sata['name'], 'Partition 1')
        self.assertEqual(next(v for v in result['volumes'] if v['mount'] == '/')['mounts'], ['/', '/alias'])
        self.assertEqual(next(d for d in result['disks'] if d['transport'] == 'sata')['media'], 'HDD')
        self.assertEqual(next(v for v in result['volumes'] if v['logical'])['name'], 'ProtonDrive')
        with patch.object(storage, 'Native') as scan:
            storage.Worker(lambda event: None).dispatch(dict(action='scan', volume=sata['id'], path=''))
            scan.assert_not_called()

    def test_btrfs_virtual_devices_share_capacity_and_physical_owner(self):
        records = storage.mounts('''1 0 0:12 /@ / rw - btrfs /dev/nvme0n1p2 rw
2 1 0:13 /@home /fakeBtrfs/home rw - btrfs /dev/nvme0n1p2 rw''')
        blocks = {'blockdevices':[{'name':'nvme0n1','path':'/dev/nvme0n1','type':'disk','maj:min':'259:0','model':'Fixture','children':[
            {'name':'nvme0n1p2','path':'/dev/nvme0n1p2','type':'part','maj:min':'259:2','size':10000}]}]}
        vfs = SimpleNamespace(f_blocks=1000, f_bfree=400, f_bavail=300, f_frsize=1, f_bsize=1)
        result = storage.discover(records, blocks, lambda _: vfs)
        self.assertEqual(len(result['volumes']), 1)
        self.assertEqual(result['disks'][0]['volumeIds'], ['0:12:btrfs'])
        self.assertFalse(result['volumes'][0]['logical'])
        self.assertEqual(storage.authorize('/fakeBtrfs/home/test', '0:12:btrfs', records)[0], '/fakeBtrfs/home/test')

    def test_blocked_capacity_does_not_hide_local_disks_or_multiply_queries(self):
        release = threading.Event()
        calls = []
        vfs = SimpleNamespace(f_blocks=1000, f_bfree=400, f_bavail=300, f_frsize=1, f_bsize=1)
        def statvfs(path):
            calls.append(path)
            if path.endswith('remote'): release.wait(2)
            return vfs
        paths = ['/fixture/cap-local', '/fixture/cap-remote']
        try:
            first = storage.volume_capacities(paths, statvfs, budget=.03)
            self.assertTrue(first[paths[0]]['accessible'])
            self.assertEqual(first[paths[1]]['error'], 'capacity-timeout')
            second = storage.volume_capacities(paths, statvfs, budget=.03)
            self.assertFalse(second[paths[1]]['accessible'])
            self.assertEqual(calls.count(paths[1]), 1)
        finally:
            release.set()



class NativeBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ei-storage-native-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.events = []
        self.worker = storage.Worker(self.events.append)
        self.addCleanup(self.worker.close)
        self.records = [dict(mountId='fixture', mount=str(self.root), root='/', source='fixture', device='1:2', fs='ext4')]
        self.patcher = patch.object(storage, 'mounts', return_value=self.records)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.assertIsNotNone(storage.native_executable(), 'Build runtime/storage in release before testing')

    def send(self, action, **fields):
        self.worker.dispatch(dict(id=len(self.events) + 1, action=action, volume='1:2:ext4', path=str(self.root), **fields))

    def scan(self):
        self.send('scan')
        self.worker.thread.join(timeout=10)
        self.assertFalse(self.worker.thread.is_alive(), self.events)
        return self.events[-1]

    def fixture(self):
        for name, size in [('home/alice', 131072), ('home/shared', 8192), ('var', 32768)]:
            path = self.root / name
            path.mkdir(parents=True)
            (path / 'data').write_bytes(b'x' * size)
        os.link(self.root / 'home/alice/data', self.root / 'var/hardlink')
        (self.root / 'loop').symlink_to('.')
        with (self.root / 'sparse').open('wb') as stream: stream.truncate(128 * 1024 * 1024)

    def test_real_scan_navigation_hardlinks_sparse_and_no_rescan(self):
        self.fixture()
        final = self.scan()
        self.assertEqual(final['event'], 'complete', final)
        self.assertEqual(final['summary']['engineState'], 'finished')
        self.assertEqual(final['summary']['errors'], 0)
        expected = int(subprocess.check_output(['du', '-sx', '-B1', str(self.root)]).split()[0])
        self.assertEqual(final['view']['bytes'], expected)
        self.assertEqual(sum(s['bytes'] for s in final['view']['segments']), expected)
        home = next(r for r in final['view']['rows'] if r['name'] == 'home')
        snapshot = final['summary']['scanId']
        # Browsing operates only on the native snapshot, including non-UTF8 IDs.
        with patch.object(storage.Native, '__init__', side_effect=AssertionError('rescan')):
            self.send('open', snapshot=snapshot, nodeId=home['nodeId'])
            view = self.events[-1]['view']
            self.assertEqual([c['name'] for c in view['rows']], ['alice', 'shared'])
            self.assertEqual(view['breadcrumbs'][-1]['nodeId'], home['nodeId'])
            self.send('open', snapshot=snapshot, nodeId=0)
            self.assertEqual(self.events[-1]['view']['bytes'], expected)

    def test_paging_filter_sort_and_others_use_all_children(self):
        (self.root / 'big').mkdir()
        (self.root / 'big/data').write_bytes(b'x' * 1024 * 1024)
        for i in range(170): (self.root / ('tiny%03d' % i)).mkdir()
        final = self.scan()
        view = final['view']
        self.assertEqual(view['count'], 171)
        self.assertEqual(len(view['rows']), 60)
        self.assertLess(len(json.dumps(final)), 50000)
        self.assertEqual(sum(s['bytes'] for s in view['segments']), view['bytes'])
        others = next(s for s in view['segments'] if s['kind'] == 'others')
        self.assertEqual(others['count'], 170)
        self.assertEqual(others['bytes'], sum(p.stat().st_blocks * 512 for p in self.root.iterdir() if p.name.startswith('tiny')))
        self.send('open', nodeId=0, others=True, offset=120)
        self.assertEqual(self.events[-1]['view']['count'], 170)
        self.assertEqual(len(self.events[-1]['view']['rows']), 50)
        self.assertFalse(self.events[-1]['view']['more'])
        self.send('open', nodeId=0, query='tiny16', order='name')
        filtered = self.events[-1]['view']
        self.assertEqual(filtered['count'], 10)
        self.assertEqual(filtered['segments'], view['segments'])
        self.assertEqual(filtered['rows'][0]['name'], 'tiny160')

    def test_non_utf8_directory_navigation_uses_native_id(self):
        raw = os.fsencode(self.root) + b'/raw-\xff'
        os.mkdir(raw)
        with open(raw + b'/file', 'wb') as stream: stream.write(b'x' * 8192)
        second = os.fsencode(self.root) + b'/raw-\xfe'
        os.mkdir(second)
        with open(second + b'/file', 'wb') as stream: stream.write(b'x' * 4096)
        final = self.scan()
        child, other = final['view']['rows']
        self.assertIn('\ufffd', child['name'])
        self.assertEqual(child['name'], other['name'])
        self.assertNotEqual(child['key'], other['key'])
        self.assertNotEqual(child['nodeId'], other['nodeId'])
        self.send('open', snapshot=final['summary']['scanId'], nodeId=child['nodeId'])
        self.assertEqual(self.events[-1]['view']['fileBytes'], 8192)

    @unittest.skipIf(os.geteuid() == 0, 'requires unprivileged fixture user')
    def test_real_warning_retains_accessible_data_and_cache(self):
        self.fixture()
        denied = self.root / 'home/denied'
        denied.mkdir()
        denied.chmod(0)
        self.addCleanup(denied.chmod, 0o700)
        final = self.scan()
        self.assertEqual(final['summary']['state'], 'complete-with-warnings', final)
        home = next(r for r in final['view']['rows'] if r['name'] == 'home')
        self.assertGreater(home['readErrors'], 0)
        self.assertTrue(home['partial'])
        self.assertGreater(home['bytes'], 131072)
        self.send('open', snapshot=final['summary']['scanId'], nodeId=home['nodeId'])
        self.assertEqual(self.events[-1]['summary']['state'], 'complete-with-warnings')
        denied_row = next(r for r in self.events[-1]['view']['rows'] if r['name'] == 'denied')
        self.send('open', snapshot=final['summary']['scanId'], nodeId=denied_row['nodeId'])
        self.assertEqual(self.events[-1]['view']['issues'][0]['errno'], 13)

    def test_failed_refresh_keeps_previous_native_snapshot(self):
        self.fixture()
        old = self.scan()
        missing = str(self.root / 'missing')
        self.worker.dispatch(dict(id=42, action='scan', volume='1:2:ext4', path=missing))
        self.worker.thread.join(timeout=10)
        self.assertEqual(self.events[-1]['event'], 'analysis-failed')
        self.assertEqual(self.events[-1]['error'], 'root_open_failed')
        self.assertNotIn('view', self.events[-1])
        self.send('open', snapshot=old['summary']['scanId'], nodeId=0)
        self.assertEqual(self.events[-1]['view'], old['view'])

    def test_cancel_never_publishes_cancelled_prefix_and_reaps_process(self):
        for i in range(1000): (self.root / str(i)).mkdir()
        self.send('scan')
        self.worker.dispatch(dict(action='cancel', id=99))
        self.worker.thread.join(timeout=10)
        self.assertFalse(self.worker.thread.is_alive())
        self.assertFalse(any(e['event'] == 'complete' for e in self.events), self.events)
        self.assertFalse(self.worker.cache)
        self.assertEqual(self.events[-1]['state'], 'cancelled')

    def test_disconnect_invalidates_cache(self):
        old = self.scan()
        self.records[0]['mountId'] = 'replaced'
        self.send('open', snapshot=old['summary']['scanId'], nodeId=0)
        self.assertEqual(self.events[-1]['error'], 'volume-disconnected')
        self.assertFalse(self.worker.cache)

    def test_native_process_death_never_publishes_or_caches_candidate(self):
        self.fixture()
        original = storage.Native.request
        def kill_after_ack(native, action, **fields):
            data = original(native, action, **fields)
            if action == 'scan':
                native.proc.kill()
                native.proc.wait(timeout=2)
            return data
        with patch.object(storage.Native, 'request', kill_after_ack):
            final = self.scan()
        self.assertEqual(final['event'], 'error', final)
        self.assertNotIn('view', final)
        self.assertFalse(self.worker.cache)

    def test_lru_evicts_native_processes_and_close_reaps_all(self):
        processes = []
        for index in range(4):
            scope = self.root / str(index)
            scope.mkdir()
            self.worker.dispatch(dict(id=index, action='scan', volume='1:2:ext4', path=str(scope)))
            self.worker.thread.join(timeout=10)
            self.assertEqual(self.events[-1]['event'], 'complete', self.events)
            processes.append(list(self.worker.cache.values())[-1].native.proc)
        self.assertEqual(len(self.worker.cache), 3)
        self.assertIsNotNone(processes[0].poll())
        self.worker.close()
        self.assertTrue(all(proc.poll() is not None for proc in processes))

    def test_stale_presentation_id_reuses_current_scope_without_retargeting_node(self):
        self.fixture()
        final = self.scan()
        snapshot_id = final['summary']['scanId']
        with patch.object(storage.Native, '__init__', side_effect=AssertionError('unnecessary scan')):
            self.send('open', snapshot='obsolete-session-id', scopeRoot=str(self.root), nodeId=999999, offset=120, query='old', others=True)
        event = self.events[-1]
        self.assertEqual(event['event'], 'view', event)
        self.assertTrue(event['viewReset'])
        self.assertEqual(event['view']['nodeId'], 0)
        self.assertEqual(event['view']['offset'], 0)
        self.assertEqual(event['summary']['scanId'], snapshot_id)

    def test_explicit_workers_reach_real_engine_and_bad_values_do_not_scan(self):
        for workers in (1, 2, 4):
            self.send('scan', workers=workers)
            self.worker.thread.join(timeout=10)
            final = self.events[-1]
            self.assertEqual(final['event'], 'complete', final)
            self.assertEqual(final['summary']['execution']['workers_limit'], workers)
        saved = list(self.worker.cache)
        for bad in (-1, 5, '4', True):
            self.send('scan', workers=bad)
            self.assertEqual(self.events[-1]['error'], 'invalid_workers')
            self.assertEqual(list(self.worker.cache), saved)

    def test_inventory_cli_and_missing_engine(self):
        with patch.dict(os.environ, DOTS_STORAGE_EXECUTABLE=str(self.root / 'not-installed')):
            self.assertFalse(storage.backend_info()['available'])
            self.send('scan')
            self.assertEqual(self.events[-1]['error'], 'native-engine-required')
        result = subprocess.run([sys.executable, str(SCRIPT)], input='invalid\n', text=True, capture_output=True, timeout=5)
        frames = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(frames[0]['event'], 'ready')
        self.assertEqual(frames[1]['error'], 'invalid-request')


class DiagnosticContractTests(unittest.TestCase):
    def test_modified_only_783_is_not_783_unreadable_entries(self):
        snapshot = storage.Snapshot(None, '/synthetic', 'fixture', ('fixture',))
        snapshot.scan_id = 'fixture'
        data = dict(total_bytes=610, issue_count=783, unstable_entries=783, unreadable_count=0,
                    excluded_count=8, directories_retained=1000, elapsed_ms=1000,
                    changes_observed=True, coverage_incomplete=False, coverage_uncertain=True,
                    uncertain_directories=783, issue_codes={'directory_changed': 783}, identity={},
                    execution=dict(workers_limit=2, workers_used=2, queue_peak=4, hardlinks_retained=0))
        summary = snapshot.complete_summary('finished', data)
        self.assertEqual(summary['state'], 'complete')
        self.assertEqual(summary['errors'], 0)
        self.assertEqual(summary['issueCount'], 783)
        self.assertTrue(summary['coverageUncertain'])
        self.assertFalse(summary['coverageIncomplete'])
        self.assertEqual(summary['excludedCount'], 8)
        self.assertEqual(summary['issueCodes'], {'directory_changed': 783})
        node = dict(subtree_issue_count=783, subtree_unreadable_count=0, subtree_unstable_entries=783,
                    changes_observed=True, coverage_incomplete=False, coverage_uncertain=True, exclusion=None)
        coverage = snapshot.coverage(node)
        self.assertEqual(coverage['readErrors'], 0)
        self.assertTrue(coverage['partial'])
        # A ctime-only observation does not claim missing coverage/entries.
        node['coverage_uncertain'] = False
        self.assertFalse(snapshot.coverage(node)['partial'])
        data.update(unreadable_count=2, issue_count=785, coverage_incomplete=True,
                    issue_codes={'directory_changed': 783, 'open_directory': 2})
        summary = snapshot.complete_summary('finished-with-warnings', data)
        self.assertEqual(summary['unreadableCount'], 2)
        self.assertEqual(summary['state'], 'complete-with-warnings')
        self.assertEqual(summary['unstableEntries'], 783)

    def test_unclassified_old_engine_result_requires_rebuild(self):
        snapshot = storage.Snapshot(None, '/synthetic', 'fixture', ('fixture',))
        with self.assertRaisesRegex(ValueError, 'native-engine-upgrade-required'):
            snapshot.complete_summary('finished', {'issue_count': 783})


class PackagingTests(unittest.TestCase):
    def test_traditional_runtime_install_and_deployed_resolution_in_temp_xdg(self):
        with tempfile.TemporaryDirectory(prefix='ei-storage-package-') as temporary:
            base = Path(temporary)
            data = base / 'data'
            env = dict(os.environ, REPO_ROOT=str(ROOT), XDG_DATA_HOME=str(data), INSTALLED_LISTFILE=str(base / 'installed'))
            # Stub only Cargo: compilation is tested separately. The real helper
            # copies the real release binary only into this temporary XDG tree.
            result = subprocess.run(['bash', '-c',
                'source "$REPO_ROOT/installer/lib/package-installers.sh"\n'
                'cargo() { [[ "$1" = build && "$2" = --locked && "$3" = --release ]]; }\n'
                'x() { "$@"; }\n'
                'install-storage-runtime'], env=env, capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            installed = data / 'dots-hyperland/storage/endless-storage'
            self.assertTrue(os.access(installed, os.X_OK))
            self.assertEqual((base / 'installed').read_text().strip(), str(installed))
            stage = base / 'shell/scripts/storage'
            stage.mkdir(parents=True)
            shutil.copy2(SCRIPT, stage / 'control.py')
            shutil.copy2(SCRIPT.with_name('inventory.py'), stage / 'inventory.py')
            spec = importlib.util.spec_from_file_location('deployed_storage', stage / 'control.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            with patch.dict(os.environ, XDG_DATA_HOME=str(data)):
                os.environ.pop('DOTS_STORAGE_EXECUTABLE', None)
                self.assertEqual(module.native_executable(), str(installed))
                bundled = base / 'shell/runtime/storage'
                bundled.mkdir(parents=True)
                (bundled / 'endless-storage').symlink_to(installed)
                self.assertEqual(module.native_executable(), str(bundled / 'endless-storage'))



if __name__ == '__main__': unittest.main()
