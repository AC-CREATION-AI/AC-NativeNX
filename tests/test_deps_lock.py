#!/usr/bin/env python3
"""deps.lock and the corresponding source archive (no network; the archive checks run when deps/dl is fetched).

Run: python3 -m unittest tests.test_deps_lock -v
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import deps  # noqa: E402

DL = Path(os.environ.get("NATIVENX_DEPS_DL") or ROOT / "deps/dl")


def fetched():
    return all((DL / deps.filename(e)).is_file() for e in deps.parse()["dep"].values())


class DepsLock(unittest.TestCase):
    def test_every_dep_is_pinned_and_licensed(self):
        entries = deps.parse()["dep"]
        self.assertGreaterEqual(len(entries), 17)
        for e in entries.values():
            self.assertRegex(e["sha256"], r"^[0-9a-f]{64}$", e["name"])
            self.assertTrue(e["url"].startswith("https://"), e["name"])
            self.assertNotIn(e["license"], ("", "-"), e["name"])
            self.assertEqual(e["source"], "yes", f"{e['name']}: the APK is built from it, its source ships")

    def test_the_inputs_named_by_the_compliance_review_are_covered(self):
        names = set(deps.parse()["dep"])
        for lock in ("sources.lock.json", "echoes-source.lock.json"):
            for s in json.loads((ROOT / "engine" / lock).read_text())["sources"]:
                self.assertIn(s["id"], names)
        self.assertLessEqual({"eden", "ffmpeg", "sdl3", "capstone"}, names)

    def test_every_cpmfile_package_is_accounted_for(self):
        cpm = deps.parse()["cpm"]
        cpmfile = json.loads((ROOT / "shell/cpmfile.json").read_text())
        self.assertEqual(set(cpm), set(cpmfile))
        self.assertEqual(len(cpm), 44)
        self.assertLessEqual({"ffmpeg-ci", "openssl-ci", "sdl3-ci", "sirit-ci"}, {k for k, v in cpmfile.items() if v.get("ci")})

    def test_the_android_build_compiles_no_shell_native_code(self):
        """The reason the cpm packages (incl. the prebuilt "ci" ones) are not corresponding source of the APK."""
        builder = (ROOT / "engine/tools/build_eden_shell.py").read_text()
        self.assertIn('"-p", shell / "src/android/raitchi-build"', builder)
        self.assertIn("Eden core must not be packaged", builder)
        for path in [ROOT / "shell/src/android/app/build.gradle.kts",
                     *(ROOT / "shell/src/android/raitchi-build").glob("*.kts"),
                     *(ROOT / "shell/src/android/raitchi-engine").glob("*.kts")]:
            text = path.read_text()
            self.assertIsNone(re.search(r"externalNativeBuild|\bcmake\s*\{|ndkBuild", text),
                              f"{path.relative_to(ROOT)} builds native code: cover it in deps.lock")

    def test_deps_lock_agrees_with_the_build(self):
        self.assertEqual(deps.consistency(DL), [])

    def test_source_archive_refuses_a_missing_upstream_archive(self):
        with tempfile.TemporaryDirectory() as empty:
            r = subprocess.run([sys.executable, str(ROOT / "tools/deps.py"), "source-tarball",
                                str(Path(empty) / "out.tar.gz"), "0.0.0", "--dir", empty],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("SOURCE_ARCHIVE_MISSING: las-android", r.stderr)
            self.assertFalse((Path(empty) / "out.tar.gz").exists())

    @unittest.skipUnless(fetched(), "run tools/deps.py fetch (or set NATIVENX_DEPS_DL) for the archive test")
    def test_source_archive_holds_every_pinned_archive_unmodified(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "AC-NativeNX-0.0.0-source.tar.gz"
            subprocess.run([sys.executable, str(ROOT / "tools/deps.py"), "source-tarball", str(out), "0.0.0",
                            "--dir", str(DL)], check=True, capture_output=True)
            with tarfile.open(out) as t:
                names = set(t.getnames())
                for member in ("AC-NativeNX-0.0.0/deps.lock", "AC-NativeNX-0.0.0/tools/deps.py",
                               "AC-NativeNX-0.0.0/SOURCE-README.md"):
                    self.assertTrue(member in names, member + " is missing (deps.lock not committed?)")
                for e in deps.parse()["dep"].values():
                    member = f"AC-NativeNX-0.0.0/deps/dl/{deps.filename(e)}"
                    self.assertTrue(member in names, member)
                    data = t.extractfile(member).read()
                    self.assertEqual(deps.hashlib.sha256(data).hexdigest(), e["sha256"], e["name"])


if __name__ == "__main__":
    unittest.main()
