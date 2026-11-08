"""run_host_checks.py on a fresh clone: exit 2 with the commands to run, not a wall of compile failures."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Precondition(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = Path(self.tmp.name) / "engine"
        (self.engine / "tools").mkdir(parents=True)
        shutil.copy2(ROOT / "tools/run_host_checks.py", self.engine / "tools")

    def tearDown(self):
        self.tmp.cleanup()

    def run_checks(self, *args):
        return subprocess.run([sys.executable, str(self.engine / "tools/run_host_checks.py"), *args],
                              capture_output=True, text=True, timeout=60)

    def test_fresh_clone_stops_with_the_commands(self):
        r = self.run_checks()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("sources/", r.stderr)
        self.assertIn("work/shared-android/", r.stderr)
        self.assertIn("python3 tools/fetch_sources.py && python3 tools/verify_sources.py"
                      " && python3 tools/build_shared_android.py", r.stderr)
        self.assertNotIn("FAILED", r.stdout)  # nothing ran
        self.assertFalse((self.engine / "build/host-checks.json").exists())

    def test_subset_only_warns(self):
        r = self.run_checks("-k", "no-such-check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("not prepared", r.stderr)

    def test_prepared_tree_runs(self):
        for rel in ("sources/las-android/runtime/ipc.h", "work/shared-android/.shared-android-stage.json"):
            (self.engine / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.engine / rel).write_text("synthetic\n")
        r = self.run_checks()
        # The check scripts are not in this temporary copy: every check is skipped, none fails.
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("not prepared", r.stderr)
        self.assertIn(" 0 failed", r.stdout)


if __name__ == "__main__":
    unittest.main()
