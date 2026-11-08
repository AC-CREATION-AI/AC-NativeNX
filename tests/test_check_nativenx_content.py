"""Tests for tools/check_nativenx_content.py (synthetic files only)."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

GUARD = Path(__file__).resolve().parents[1] / "tools" / "check_nativenx_content.py"


def run_guard(root: Path):
    return subprocess.run([sys.executable, str(GUARD), str(root)], capture_output=True, text=True)


class NativeNXContentTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def put(self, rel, data=b"x"):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def test_clean_tree_passes(self):
        self.put("engine/tools/build_eden_shell.py")
        self.put("docs/private-notes.md")
        r = run_guard(self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_flags_local_only_dirs_at_any_depth(self):
        for rel in ("private/raitchi-shell-signing/password.txt",
                    "engine/private/las-baseline/extracted/exefs/main",
                    "engine/evidence/las-inputs.json",
                    "copy/raitchi-shell-signing/test.jks"):
            self.put(rel)
        r = run_guard(self.root)
        self.assertEqual(r.returncode, 1)
        for rel in ("private/raitchi-shell-signing/password.txt",
                    "engine/private/las-baseline/extracted/exefs/main",
                    "engine/evidence/las-inputs.json", "copy/raitchi-shell-signing/test.jks"):
            self.assertIn(rel, r.stderr)

    def test_git_tree_ignored_private_passes_forced_add_fails(self):
        subprocess.run(["git", "-C", str(self.root), "init", "-q"], check=True)
        self.put(".gitignore", b"/private/\n")
        self.put("private/raitchi-shell-signing/password.txt")
        r = run_guard(self.root)
        self.assertEqual(r.returncode, 0, r.stderr)  # the developer's own key, ignored
        subprocess.run(["git", "-C", str(self.root), "add", "-f",
                        "private/raitchi-shell-signing/password.txt"], check=True)
        r = run_guard(self.root)
        self.assertEqual(r.returncode, 1, r.stdout)  # `git add -f` does not get through
        self.assertIn("private/raitchi-shell-signing/password.txt", r.stderr)


if __name__ == "__main__":
    unittest.main()
