#!/usr/bin/env python3
"""Local release archive skeleton; packages exact files, never builds or uploads."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import stat
import tarfile
import zipfile


def regular(path, allow_hardlink=False):
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise ValueError(f"Symlinks are forbidden: {path}")
    meta = path.stat()
    if not stat.S_ISREG(meta.st_mode) or not allow_hardlink and meta.st_nlink != 1:
        raise ValueError(f"Expected a single-link regular file: {path}")
    return path.read_bytes()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='New output directory under canonical /tmp')
    parser.add_argument('--version', required=True)
    parser.add_argument('--format', choices=['tar.gz', 'zip'], default='tar.gz')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,80}', args.version):
        parser.error('Unsafe version identifier')
    output = args.output.absolute()
    if output != output.resolve() or not output.is_relative_to('/tmp') or output == Path('/tmp') or output.is_relative_to(Path.home().resolve()) or output.exists():
        parser.error('Output must be a new canonical directory below /tmp, outside HOME')
    if any(p.is_symlink() for p in output.parents):
        parser.error('Symlink output parent is forbidden')
    bundle = args.bundle.absolute()
    manifest_bytes = regular(bundle / 'manifest.json')
    manifest = json.loads(manifest_bytes)
    if manifest['schema'] != 1 or manifest['completeness'] != 'subset':
        parser.error('Only schema 1 experimental subsets can be packaged')
    if args.version != manifest['payload_version']:
        parser.error('Archive version must match the declared payload version')
    # Cargo may hardlink its output to target/*/deps. Snapshot its bytes as a
    # REGULAR archive member; never preserve archive links or traverse a symlink.
    entries = {'endless-setup': (regular(args.binary.absolute(), allow_hardlink=True), 0o755), 'bundle/manifest.json': (manifest_bytes, 0o644)}
    for row in manifest['files'] + manifest.get('assets', []):
        source = row['source']
        if '\\' in source or any(p in ('', '.', '..') for p in source.split('/')) or any(ord(c) < 32 for c in source):
            parser.error('Unsafe bundle source')
        data = regular(bundle / source)
        if hashlib.sha256(data).hexdigest() != row['sha256']:
            parser.error(f'Digest mismatch: {source}')
        name = 'bundle/' + source
        if name in entries:
            parser.error('Duplicate archive entry')
        entries[name] = (data, 0o644)
    output.mkdir(mode=0o700, parents=True)
    prefix = f'endless-setup-{args.version}-{platform.machine()}-linux-experimental'
    archive = output / f'{prefix}.{args.format}'
    if args.format == 'tar.gz':
        import io
        with tarfile.open(archive, 'x:gz') as stream:
            for name, (data, mode) in entries.items():
                info = tarfile.TarInfo(prefix + '/' + name)
                info.size, info.mode, info.mtime = len(data), mode, 0
                stream.addfile(info, io.BytesIO(data))
    else:
        with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as stream:
            for name, (data, mode) in entries.items():
                info = zipfile.ZipInfo(prefix + '/' + name, (1980, 1, 1, 0, 0, 0))
                info.external_attr = (stat.S_IFREG | mode) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                stream.writestr(info, data)
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    with (output / 'SHA256SUMS').open('x') as stream:
        stream.write(f'{checksum}  {archive.name}\n')
    print(f'Local experimental archive: {archive}. Not signed, uploaded or published.')


if __name__ == '__main__':
    main()
