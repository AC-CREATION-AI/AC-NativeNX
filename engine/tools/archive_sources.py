"""Locked archive inputs for builds from a corresponding-source distribution."""
import json
import os
from pathlib import Path, PurePosixPath
import sys
import tarfile
import verify_sources

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent / 'tools'))
import deps


def extract(archive, destination):
    """Extract only archive members, stripping the upstream root; never copy tree extras."""
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as stream:
        members = []
        for member in stream.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or '.git' in path.parts:
                raise ValueError('Unsafe upstream archive path')
            if len(path.parts) < 2:
                continue
            member.name = str(PurePosixPath(*path.parts[1:]))
            members.append(member)
        stream.extractall(destination, members=members, filter='data')


def verified(source):
    pinned = deps.parse()['dep']
    directory = Path(os.environ.get('NATIVENX_DEPS_DL') or ROOT.parent / 'deps/dl')
    errors, _ = verify_sources.verify_archive(source, pinned, directory)
    if errors:
        raise RuntimeError('; '.join(errors))
    return directory / deps.filename(pinned[source['id']])


def verify_locks():
    for name in ('sources.lock.json', 'echoes-source.lock.json'):
        for source in json.loads((ROOT / name).read_text())['sources']:
            if not (ROOT / source['path'] / '.git').exists():
                verified(source)
            else:
                errors, _ = verify_sources.verify_git(source)
                if errors:
                    raise RuntimeError('; '.join(errors))
