#!/usr/bin/env python3
"""Read-only mount/physical-device inventory; never enumerates file trees."""
import os
from pathlib import Path
import re
import json
import subprocess
import threading
import time

PSEUDO = {'proc', 'sysfs', 'devtmpfs', 'devpts', 'tmpfs', 'cgroup', 'cgroup2',
          'securityfs', 'debugfs', 'tracefs', 'configfs', 'pstore', 'mqueue',
          'efivarfs', 'bpf', 'fuse.portal', 'fuse.gvfsd-fuse', 'ramfs',
          'hugetlbfs', 'autofs', 'fusectl', 'rpc_pipefs', 'nsfs', 'binfmt_misc', 'squashfs'}

def unescape(value):
    return re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), value)


def mounts(text=None):
    if text is None:
        text = Path('/proc/self/mountinfo').read_text(errors='surrogateescape')
    result = []
    for line in text.splitlines():
        try:
            left, right = line.split(' - ', 1)
            fields, fs = left.split(), right.split()
            result.append(dict(mountId=fields[0], device=fields[2], root=unescape(fields[3]),
                               mount=unescape(fields[4]), fs=fs[0], source=unescape(fs[1])))
        except (ValueError, IndexError):
            continue
    return result


def capacity(s):
    unit = s.f_frsize or s.f_bsize
    total = max(0, s.f_blocks * unit)
    free = min(total, max(0, s.f_bfree * unit))
    available = min(free, max(0, s.f_bavail * unit))
    used, reserved = total - free, free - available
    return dict(total=total, used=used, available=available, reserved=reserved,
                percent=100 * used / total if total else 0,
                low=bool(total and available / total < .1))


def filesystem_group(record):
    if record['fs'] == 'btrfs':
        return 'btrfs:' + os.path.realpath(record['source'])
    return record['device'] + ':' + record['fs']


def mount_preference(record):
    return (record['mount'] != '/', record.get('root', '/') != '/', len(record['mount']), record['mount'])


_capacity_jobs = {}
_capacity_lock = threading.Lock()


def volume_capacities(paths, statvfs=os.statvfs, budget=1.5):
    """Bound network statvfs latency without blocking discovery of local disks.

    Reuse an in-flight query on subsequent refreshes rather than piling up
    uninterruptible filesystem calls. Only our worker owns these daemon threads.
    """
    jobs = {}
    deadline = time.monotonic() + budget
    with _capacity_lock:
        for path in paths:
            old = _capacity_jobs.get(path)
            if old and not old['done'].is_set():
                jobs[path] = old
                continue
            # Completed results are refreshed; disconnected completed jobs go away.
            for key in list(_capacity_jobs):
                if key not in paths and _capacity_jobs[key]['done'].is_set(): del _capacity_jobs[key]
            if len([j for j in _capacity_jobs.values() if not j['done'].is_set()]) >= 32:
                continue
            job = dict(done=threading.Event(), result=None)
            _capacity_jobs[path] = jobs[path] = job
            def query(path=path, job=job):
                try: job['result'] = dict(accessible=True, **capacity(statvfs(path)))
                except OSError as e: job['result'] = dict(accessible=False, error=type(e).__name__)
                finally: job['done'].set()
            threading.Thread(target=query, daemon=True).start()
    result = {}
    for path, job in jobs.items():
        job['done'].wait(max(0, deadline - time.monotonic()))
        result[path] = job['result'] if job['done'].is_set() else dict(accessible=False, error='capacity-timeout')
    return result


def inventory(records=None, statvfs=os.statvfs):
    records = mounts() if records is None else records
    groups = {}
    for m in records:
        if m['fs'] in PSEUDO or (m['fs'] == 'overlay' and m['mount'] != '/'):
            continue
        # Filesystem identity, not mount ID: bind aliases and Btrfs subvolumes
        # share capacity. Keep mount locations for selecting an analysis root.
        key = filesystem_group(m)
        groups.setdefault(key, []).append(m)
    volumes = []
    for key, group in groups.items():
        group.sort(key=mount_preference)
        m = group[0]
        locations = sorted({a['mount'] for a in group})
        physical = ''
        try:
            node = Path('/sys/dev/block', m['device']).resolve(strict=True)
            physical = node.parent.name if (node / 'partition').exists() else node.name
        except OSError:
            pass
        v = dict(id=m['device'] + ':' + m['fs'], mount=m['mount'], mounts=locations, fs=m['fs'],
                 source=m['source'], physical=physical,
                 name='System' if m['mount'] == '/' else os.path.basename(m['mount']) or m['source'],
                 accessible=True)
        volumes.append(v)
    readings = volume_capacities([v['mount'] for v in volumes], statvfs)
    for volume in volumes:
        volume.update(readings.get(volume['mount'], dict(accessible=False, error='capacity-busy')))
    return sorted(volumes, key=lambda v: (v['mount'] != '/', v['mount']))


def block_devices():
    """Explicit allowlist: never ask lsblk for serials, UUIDs or WWNs."""
    try:
        result = subprocess.run(['lsblk', '-J', '-b', '-o',
                                 'NAME,KNAME,PATH,TYPE,SIZE,MODEL,ROTA,TRAN,RM,MAJ:MIN,FSTYPE,LABEL,PKNAME'],
                                capture_output=True, timeout=4)
        if result.returncode: raise ValueError('lsblk-failed')
        return json.loads(result.stdout), ''
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {'blockdevices': []}, 'physical-inventory-unavailable'


def discover(records=None, blocks=None, statvfs=os.statvfs):
    records = mounts() if records is None else records
    volumes = inventory(records, statvfs)
    warning = ''
    if blocks is None: blocks, warning = block_devices()
    disks, index, owners = [], {}, {}
    def visit(node, owner=''):
        name = node.get('kname') or node.get('name', '')
        if name.startswith(('zram', 'loop', 'ram')): return
        identity = str(node.get('maj:min', ''))
        if node.get('type') == 'disk':
            owner = 'disk:' + identity
            if not any(d['id'] == owner for d in disks):
                disks.append(dict(id=owner, name=(node.get('model') or name).strip(),
                                  source=node.get('path', '/dev/' + name), physical=name,
                                  size=int(node.get('size') or 0), disk=True, mounted=False,
                                  transport=node.get('tran') or '', removable=bool(node.get('rm')),
                                  media='HDD' if node.get('rota') is True or node.get('rota') == 1
                                  else 'SSD' if node.get('rota') is False or node.get('rota') == 0 else '',
                                  volumeIds=[]))
        if identity:
            index[identity] = node
            owners.setdefault(identity, [])
            if owner and owner not in owners[identity]: owners[identity].append(owner)
        for child in node.get('children', []): visit(child, owner)
    for node in blocks.get('blockdevices', []): visit(node)
    mounted_devices = set()
    for volume in volumes:
        device = volume['id'].rsplit(':', 1)[0]
        mounted_devices.add(device)
        node = index.get(device, {})
        # Btrfs reports a virtual device number; encrypted/mapper sources may
        # also have a different spelling than lsblk's canonical block path.
        if not node and volume['source'].startswith('/dev/'):
            source = os.path.realpath(volume['source'])
            node = next((b for b in index.values() if b.get('path') and os.path.realpath(b['path']) == source), {})
        block_id = str(node.get('maj:min') or device)
        mounted_devices.add(block_id)
        volume.update(mounted=True, disk=False, owners=owners.get(block_id, []),
                      label=node.get('label') or '', size=int(node.get('size') or volume.get('total', 0)),
                      logical=not bool(owners.get(block_id)))
        mount = volume['mount']
        if node.get('label'): volume['name'] = node['label']
        elif mount == '/': volume['name'] = 'System'
        elif mount == '/boot': volume['name'] = 'Boot'
        elif re.fullmatch(r'[0-9a-fA-F-]{20,}', os.path.basename(mount)):
            volume['name'] = 'Partition ' + re.search(r'\d+$', node.get('kname', '1'))[0] if re.search(r'\d+$', node.get('kname', '1')) else 'Volume'
        volume['mountToken'] = next((m.get('mountId', '') for m in records if m['mount'] == mount), '')
    for device, node in index.items():
        if device in mounted_devices or not owners.get(device): continue
        # An unformatted disk with partitions is represented by its disk card;
        # partitions, encrypted containers and logical block volumes remain visible.
        if node.get('type') == 'disk' and node.get('children'): continue
        if node.get('fstype') == 'swap': continue
        number = re.search(r'\d+$', node.get('kname') or node.get('name', ''))
        volumes.append(dict(id='block:' + device, name=node.get('label') or
                            ('Partition ' + number[0] if node.get('type') == 'part' and number else node.get('name', 'Volume')),
                            source=node.get('path', ''), fs=node.get('fstype') or node.get('type', ''),
                            size=int(node.get('size') or 0), mount='', mounts=[], mounted=False,
                            disk=False, accessible=False, owners=owners[device], logical=False))
    for disk in disks:
        disk['volumeIds'] = [v['id'] for v in volumes if disk['id'] in v['owners']]
    return dict(volumes=volumes, disks=disks, warning=warning)


def inside(path, root):
    return path == root or path.startswith(root.rstrip('/') + '/')


def authorize(path, volume, records):
    if not isinstance(path, str) or not os.path.isabs(path) or '\x00' in path:
        raise ValueError('invalid-path')
    path = os.path.normpath(path)
    # Reject symlinks in every component; realpath alone could silently change
    # the requested location. The traversal itself uses directory FDs as well.
    if os.path.realpath(path) != path:
        raise ValueError('symlink-path')
    matches = [m for m in records if inside(path, m['mount'])]
    if not matches:
        raise ValueError('volume-disconnected')
    current = max(matches, key=lambda m: len(m['mount']))
    canonical = min((m for m in records if filesystem_group(m) == filesystem_group(current)), key=mount_preference)
    if canonical['device'] + ':' + canonical['fs'] != volume:
        raise ValueError('outside-volume')
    if inside(path, '/root'):
        raise ValueError('protected-path')
    return path, current


def open_directory(path):
    """Pin the authorized root without following a symlink in any component."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open('/', flags)
    try:
        for part in path.split('/'):
            if not part:
                continue
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise

