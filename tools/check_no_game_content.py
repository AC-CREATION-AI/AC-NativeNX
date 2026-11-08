#!/usr/bin/env python3
"""Refuse game content, console keys, signing material and oversized blobs in a source tree.

    python3 tools/check_no_game_content.py [root]

Exit status 0 = clean, 1 = at least one file refused. Every refused file is named
in the message. The guard never edits or deletes anything.

Files checked: when root is the top of a git work tree, every file git could commit
(tracked or staged, plus untracked files that are not ignored), so ignored local
build outputs do not fail the check but a `git add -f` does; otherwise (CI archive,
copy, plain directory) every file under root.

Refused:
  * game packages / containers: .nsp .xci .nsz .xcz .nca .ncz .tik
  * Switch executables and metadata: .nso .nro .npdm .kip, and romfs.bin / exefs.bin
  * Switch system fonts: .bfttf .bfs
  * key files: prod.keys, title.keys, anything ending in .keys, and renamed copies
    such as PROD.KEYS.txt or prod.keys.bak (any name containing ".keys.")
  * signing material: .jks .keystore .p12 .pfx .pem .der .key
  * directories named romfs/, exefs/, extracted/ (game data), save/ (saves) or
    mods/ (mods are built from game files)
  * any single file larger than 50 MB (APKs, dumps, caches do not belong in git)

The guard looks at names and sizes only. Key *contents* (a header_key line in an .ini,
a PEM private key in a .txt, a literal keystore password) are refused by
tools/check_no_secrets.py, which CI runs next to this guard.

AC-NativeNX never ships or needs any of these: users bring their own game and keys.
"""
import os
import subprocess
import sys
from pathlib import Path

BANNED_EXTENSIONS = {".nsp", ".xci", ".nsz", ".xcz", ".nca", ".ncz", ".tik"}
EXECUTABLE_EXTENSIONS = {".nso", ".nro", ".npdm", ".kip"}
FONT_EXTENSIONS = {".bfttf", ".bfs"}
SIGNING_EXTENSIONS = {".jks", ".keystore", ".p12", ".pfx", ".pem", ".der", ".key"}
BANNED_NAMES = {"romfs.bin", "exefs.bin"}
BANNED_DIRS = {"romfs", "exefs", "extracted", "save", "mods"}
MAX_BYTES = 50 * 1024 * 1024
SKIP_DIRS = {".git"}


def is_work_tree_top(root: Path) -> bool:
    try:
        top = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True)
    except FileNotFoundError:
        return False
    return top.returncode == 0 and Path(top.stdout.strip()).resolve() == root.resolve()


def candidate_files(root: Path):
    """Relative posix paths of the files that could end up in a commit."""
    if is_work_tree_top(root):
        out = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others",
                              "--exclude-standard"], capture_output=True, check=True).stdout
        yield from sorted(set(out.decode("utf-8", "surrogateescape").split("\0")) - {""})
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            yield (Path(dirpath) / name).relative_to(root).as_posix()


def scan(root: Path):
    """Yield (relative_posix_path, reason) for each offending file."""
    for rel in candidate_files(root):
        *dirs, name = rel.split("/")
        lower = name.lower()
        suffix = Path(lower).suffix
        if any(part.lower() in BANNED_DIRS for part in dirs):
            yield rel, ("inside a romfs/, exefs/, extracted/, save/ or mods/ directory "
                        "(game data, saves or mods)")
        elif suffix in BANNED_EXTENSIONS:
            yield rel, f"game package/container ({suffix})"
        elif suffix in EXECUTABLE_EXTENSIONS or lower in BANNED_NAMES:
            yield rel, f"Switch executable or game data ({name})"
        elif suffix in FONT_EXTENSIONS:
            yield rel, f"Switch system font ({suffix})"
        elif lower.endswith(".keys") or ".keys." in lower:
            yield rel, "console key file"
        elif suffix in SIGNING_EXTENSIONS:
            yield rel, f"signing material ({suffix})"
        else:
            try:
                size = (root / rel).stat().st_size
            except OSError:
                continue  # deleted from the work tree but still in the index
            if size > MAX_BYTES:
                yield rel, f"file larger than 50 MB ({size // (1024 * 1024)} MB)"


def main(argv) -> int:
    root = Path(argv[1] if len(argv) > 1 else Path(__file__).resolve().parents[1])
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2
    findings = list(scan(root))
    if findings:
        print("REFUSED: game content, keys or oversized files found:", file=sys.stderr)
        for rel, reason in findings:
            print(f"  {rel}  --  {reason}", file=sys.stderr)
        print("Please remove these files from the commit (git rm --cached, then add them to "
              "your local ignore file). This project never contains games, keys or "
              "firmware. See CONTRIBUTING.md.", file=sys.stderr)
        return 1
    print(f"OK: no game content, keys or oversized files under {root}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
