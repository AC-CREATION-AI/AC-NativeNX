#!/usr/bin/env python3
"""Verify the pinned upstream inputs without fetching or modifying them.

Default: each source is a Git checkout at the locked commit and origin, with no tracked file modified.
--archives [DIR]: no Git metadata needed, for a tree unpacked from the corresponding source archive
(SOURCE-README.md). Each source's upstream archive in DIR (default $NATIVENX_DEPS_DL or deps/dl) must be
the deps.lock `dep` bound to the lock's commit and URL and have its pinned sha256, and every file it holds
must be present and unmodified under the source path.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def git(path, *args):
    return subprocess.check_output(
        ["git", "-C", str(path), *args], text=True, stderr=subprocess.STDOUT
    ).strip()


def verify_git(source):
    path = ROOT / source["path"]
    head = git(path, "rev-parse", "HEAD")
    origin = git(path, "remote", "get-url", "origin")
    dirty = git(path, "status", "--porcelain", "--untracked-files=no")
    errors = []
    if head != source["commit"]:
        errors.append("commit differs from lock")
    if origin != source["url"]:
        errors.append("origin differs from lock")
    if dirty:
        errors.append("tracked upstream files modified")
    return errors, head[:12]


def digest(f):
    h = hashlib.sha256()
    for b in iter(lambda: f.read(1 << 20), b""):
        h.update(b)
    return h.hexdigest()


def verify_archive(source, pinned, dl):
    import deps  # tools/deps.py, the deps.lock reader
    label = f"archive {source['commit'][:12]}"
    e = pinned.get(source["id"])
    if e is None:
        return ["not a `dep` of deps.lock"], label
    errors = []
    if e["version"] != source["commit"]:
        errors.append("deps.lock commit differs from lock")
    if e["url"] != f"{source['url'].removesuffix('.git')}/archive/{source['commit']}.tar.gz":
        errors.append("deps.lock archive URL differs from lock")
    archive = dl / deps.filename(e)
    if not archive.is_file():
        return errors + [f"archive missing: {archive}"], label
    if deps.sha256(archive) != e["sha256"]:
        return errors + ["archive sha256 differs from deps.lock"], label
    path = ROOT / source["path"]
    changed = 0
    with tarfile.open(archive) as t:
        for m in t:
            # Upstream /archive/<commit>.tar.gz files hold a single <repo>-<commit>/ directory.
            parts = PurePosixPath(m.name).parts[1:]
            if PurePosixPath(m.name).is_absolute() or ".." in parts:
                return errors + [f"unsafe archive member {m.name}"], label
            if not parts or not (m.isfile() or m.issym()):
                continue
            target = path.joinpath(*parts)
            if m.issym():
                changed += not (target.is_symlink() and os.readlink(target) == m.linkname)
            elif target.is_symlink() or not target.is_file():
                changed += 1
            else:
                with open(target, "rb") as f:
                    changed += digest(f) != digest(t.extractfile(m))
    if changed:
        errors.append(f"{changed} archived file(s) missing or modified under {source['path']}")
    return errors, label


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lock", type=Path, default=ROOT / "sources.lock.json",
                        help="Source lock to verify; paths remain relative to the workspace")
    parser.add_argument("--archives", type=Path, nargs="?", metavar="DIR",
                        const=Path(os.environ.get("NATIVENX_DEPS_DL") or ROOT.parent / "deps/dl"),
                        help="Verify unpacked upstream archives against deps.lock instead of Git checkouts")
    args = parser.parse_args()
    lock = json.loads(args.lock.read_text())
    if args.archives:
        sys.path.insert(0, str(ROOT.parent / "tools"))
        import deps
        pinned = deps.parse()["dep"]
    failed = False
    for source in lock["sources"]:
        try:
            errors, label = verify_archive(source, pinned, args.archives) if args.archives else verify_git(source)
            failed |= bool(errors)
            print(f"{source['id']}: {'FAIL: ' + ', '.join(errors) if errors else 'OK'} ({label})")
        except (OSError, subprocess.CalledProcessError, tarfile.TarError) as exc:
            print(f"{source['id']}: FAIL: {exc}")
            failed = True
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
