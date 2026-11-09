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


class VerifySourcesWithoutGit(unittest.TestCase):
    """verify_sources.py --archives on a tree unpacked from a source archive: no .git anywhere."""
    COMMIT = "0123456789abcdef0123456789abcdef01234567"

    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        for f in ("engine/tools/verify_sources.py", "tools/deps.py"):
            (self.tmp / f).parent.mkdir(parents=True, exist_ok=True)
            (self.tmp / f).write_bytes((ROOT / f).read_bytes())
        top = self.tmp / "upstream" / f"demo-{self.COMMIT}"
        (top / "src").mkdir(parents=True)
        (top / "README.md").write_text("demo\n")
        (top / "src/main.c").write_text("int main(void) { return 0; }\n")
        self.archive = self.tmp / f"deps/dl/demo-{self.COMMIT}.tar.gz"
        self.archive.parent.mkdir(parents=True)
        with tarfile.open(self.archive, "w:gz") as t:
            t.add(top, arcname=top.name)
        url = "https://example.invalid/acme/demo"
        (self.tmp / "deps.lock").write_text(f"dep | demo | {self.COMMIT} | MIT | yes | "
                                            f"{deps.sha256(self.archive)} | {url}/archive/{self.COMMIT}.tar.gz\n")
        (self.tmp / "engine/sources.lock.json").write_text(json.dumps({"schema": 1, "sources": [
            {"id": "demo", "url": url + ".git", "path": "sources/demo", "commit": self.COMMIT}]}))
        # As SOURCE-README.md says: tar -xzf deps/dl/<archive> -C engine/sources/demo --strip-components=1
        with tarfile.open(self.archive) as t:
            t.extractall(self.tmp / "unpack", filter="data")
        (self.tmp / "engine/sources").mkdir()
        (self.tmp / "unpack" / top.name).rename(self.tmp / "engine/sources/demo")

    def verify(self, *extra):
        env = {k: v for k, v in os.environ.items() if k != "NATIVENX_DEPS_DL"}
        return subprocess.run([sys.executable, "tools/verify_sources.py", *extra], cwd=self.tmp / "engine",
                              capture_output=True, text=True, env=env)

    def test_unpacked_tree_verifies_without_git(self):
        self.assertEqual(list(self.tmp.rglob(".git")), [])
        self.assertNotEqual(self.verify().returncode, 0, "the Git mode cannot verify an unpacked tree")
        r = self.verify("--archives")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("demo: OK (archive 0123456789ab)", r.stdout)

    def test_altered_archive_is_refused(self):
        with open(self.archive, "ab") as f:
            f.write(b"\0")
        r = self.verify("--archives")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("archive sha256 differs from deps.lock", r.stdout)

    def test_modified_or_missing_unpacked_file_is_refused(self):
        (self.tmp / "engine/sources/demo/src/main.c").write_text("int main(void) { return 1; }\n")
        (self.tmp / "engine/sources/demo/README.md").unlink()
        r = self.verify("--archives")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("2 archived file(s) missing or modified under sources/demo", r.stdout)

    def test_lock_and_deps_lock_must_name_the_same_commit(self):
        lock = self.tmp / "engine/sources.lock.json"
        lock.write_text(lock.read_text().replace(self.COMMIT, "f" * 40))
        r = self.verify("--archives")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("deps.lock commit differs from lock", r.stdout)


if __name__ == "__main__":
    unittest.main()
