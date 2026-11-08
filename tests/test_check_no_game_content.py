"""Tests for tools/check_no_game_content.py (synthetic files only)."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

GUARD = Path(__file__).resolve().parents[1] / "tools" / "check_no_game_content.py"


def run_guard(root: Path):
    return subprocess.run([sys.executable, str(GUARD), str(root)],
                          capture_output=True, text=True)


class GuardTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def put(self, rel, data=b"x"):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p

    def assert_refused(self, rel):
        r = run_guard(self.root)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(rel, r.stderr)  # message names the offending path

    def test_clean_tree_passes(self):
        self.put("README.md", b"hello")
        self.put("src/main.c", b"int main(){}")
        r = run_guard(self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("OK", r.stdout)

    def test_flags_nsp(self):
        self.put("foo.nsp")
        self.assert_refused("foo.nsp")

    def test_flags_other_game_extensions(self):
        for ext in (".xci", ".nsz", ".xcz", ".nca", ".tik"):
            with self.subTest(ext=ext):
                self.put("dump/game" + ext)
                self.assert_refused("dump/game" + ext)
                (self.root / ("dump/game" + ext)).unlink()

    def test_extension_check_is_case_insensitive(self):
        self.put("GAME.NSP")
        self.assert_refused("GAME.NSP")

    def test_flags_prod_keys(self):
        self.put("keys/prod.keys")
        self.assert_refused("keys/prod.keys")

    def test_flags_title_and_any_keys_file(self):
        self.put("title.keys")
        self.put("my.keys")
        r = run_guard(self.root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("title.keys", r.stderr)
        self.assertIn("my.keys", r.stderr)

    def test_flags_romfs_and_exefs_dirs(self):
        self.put("romfs/a.bin")
        self.put("x/exefs/main")
        r = run_guard(self.root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("romfs/a.bin", r.stderr)
        self.assertIn("x/exefs/main", r.stderr)

    def test_flags_switch_executables_and_fonts(self):
        for rel in ("exe/main.nso", "exe/game.NRO", "exe/main.npdm", "exe/fs.kip",
                    "dump/romfs.bin", "dump/exefs.bin", "font/nintendo.bfttf", "dump/c.ncz"):
            with self.subTest(rel=rel):
                self.put(rel)
                self.assert_refused(rel)
                (self.root / rel).unlink()

    def test_flags_renamed_key_files(self):
        for rel in ("PROD.KEYS.txt", "backup/prod.keys.bak", "title.keys.old"):
            with self.subTest(rel=rel):
                self.put(rel)
                self.assert_refused(rel)
                (self.root / rel).unlink()

    def test_flags_signing_material(self):
        for ext in (".jks", ".keystore", ".p12", ".pfx", ".pem", ".der", ".key"):
            with self.subTest(ext=ext):
                self.put("sign/release" + ext)
                self.assert_refused("sign/release" + ext)
                (self.root / ("sign/release" + ext)).unlink()

    def test_flags_save_mods_and_extracted_dirs(self):
        self.put("save/progress.dat")
        self.put("a/mods/patch.txt")
        self.put("b/Extracted/main")
        r = run_guard(self.root)
        self.assertEqual(r.returncode, 1)
        for rel in ("save/progress.dat", "a/mods/patch.txt", "b/Extracted/main"):
            self.assertIn(rel, r.stderr)

    def test_similar_names_pass(self):
        # Source files of an emulator frontend legitimately say "keys", "save" or "mod".
        for rel in ("src/hotkeys.cpp", "src/keys_ui.h", "src/savedata/save_data.cpp",
                    "src/mods.c", "docs/romfs.md", "src/key_manager.cpp"):
            self.put(rel)
        r = run_guard(self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_git_tree_checks_what_could_be_committed(self):
        subprocess.run(["git", "-C", str(self.root), "init", "-q"], check=True)
        self.put(".gitignore", b"/build/\n")
        self.put("build/test-results/debug.keystore")  # ignored local test output
        self.assertEqual(run_guard(self.root).returncode, 0)
        self.put("new/release.jks")  # untracked, not ignored: could be committed
        self.assert_refused("new/release.jks")
        (self.root / "new/release.jks").unlink()
        subprocess.run(["git", "-C", str(self.root), "add", "-f", "build/test-results/debug.keystore"],
                       check=True)
        self.assert_refused("build/test-results/debug.keystore")  # `git add -f` does not get through

    def test_flags_big_file(self):
        p = self.root / "blob.dat"
        with open(p, "wb") as f:  # sparse 60 MB
            f.truncate(60 * 1024 * 1024)
        self.assert_refused("blob.dat")

    def test_file_under_limit_passes(self):
        p = self.root / "ok.dat"
        with open(p, "wb") as f:
            f.truncate(10 * 1024 * 1024)
        self.assertEqual(run_guard(self.root).returncode, 0)

    def test_git_dir_is_ignored(self):
        self.put(".git/objects/foo.nsp")
        self.assertEqual(run_guard(self.root).returncode, 0)

    def test_message_explains_what_to_do(self):
        self.put("a.xci")
        r = run_guard(self.root)
        self.assertIn("a.xci", r.stderr)
        self.assertIn("remove", r.stderr.lower())


if __name__ == "__main__":
    unittest.main()
