#!/usr/bin/env python3
"""Refuse AC-NativeNX's local-only material in what could be committed.

The engine tools write private material next to the sources: the local test signing
key (`private/raitchi-shell-signing/`), the user's extracted game
(`private/*-baseline/extracted/`) and run evidence (`evidence/`). Only `.gitignore`
keeps them out, and `git add -f` goes through it; this guard does not.

    python3 tools/check_nativenx_content.py [root]

Files checked: when root is the top of a git work tree, every file git could commit
(tracked or staged, plus untracked files that are not ignored), so a developer's own
ignored `private/` does not fail the check but a forced add does; otherwise every
file under root. The generic rules (game files, keys, signing material, saves) live
in tools/check_no_game_content.py and tools/check_no_secrets.py.

Exit status 0 = clean, 1 = refused (with the offending paths listed).
"""
import sys
from pathlib import Path

from check_no_game_content import candidate_files  # same git-aware file selection

ROOT = Path(__file__).resolve().parents[1]

# Directory names the engine tools use for local-only material, at any depth
# (`private/` exists both at the root and under `engine/`).
FORBIDDEN_DIRS = {
    "private": "local-only private material (signing key, extracted game)",
    "evidence": "local run evidence",
    "raitchi-shell-signing": "local test signing key",
}


def reason_for(rel: str) -> str:
    """Return why the path is forbidden, or an empty string if it is fine."""
    for part in rel.lower().split("/")[:-1]:
        if part in FORBIDDEN_DIRS:
            return FORBIDDEN_DIRS[part]
    return ""


def main(argv) -> int:
    root = Path(argv[1]) if len(argv) > 1 else ROOT
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2
    findings = sorted({(rel, reason_for(rel)) for rel in candidate_files(root) if reason_for(rel)})
    if findings:
        print("REFUSED: AC-NativeNX local-only material found:", file=sys.stderr)
        for rel, reason in findings:
            print(f"  {rel} — {reason}", file=sys.stderr)
        print("Remove it from the commit (git rm --cached); it must stay on your machine.",
              file=sys.stderr)
        return 1

    print(f"OK: no AC-NativeNX local-only material under {root}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
