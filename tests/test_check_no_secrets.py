"""Tests for tools/check_no_secrets.py (synthetic files only).

Every fake secret is assembled at run time so that this file itself stays clean.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCANNER = Path(__file__).resolve().parents[1] / "tools" / "check_no_secrets.py"

FAKE_HEX = "0123456789abcdef" * 2
STORE = "store" + "Password"


def run_scanner(root: Path, *args):
    return subprocess.run([sys.executable, str(SCANNER), *args, str(root)],
                          capture_output=True, text=True)


def git(root: Path, *args):
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t",
                    "-c", "commit.gpgsign=false", *args], check=True, capture_output=True)


class SecretScannerTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def put(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    def assert_refused(self, rel, *args):
        r = run_scanner(self.root, *args)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(rel, r.stderr)
        return r

    def assert_clean(self, *args):
        r = run_scanner(self.root, *args)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("OK", r.stdout)
        return r

    def test_clean_tree_passes(self):
        self.put("README.md", "header_key is read from the user's own prod.keys\n")
        self.put("src/keys.c", 'get("master_key_00", 16, mk);\n')
        self.assert_clean()

    def test_console_key_line_in_any_file(self):
        for rel, line in (("a/backup.ini", "header" + "_key = " + FAKE_HEX * 2),
                          ("b/notes.txt", "  key_area_key" + "_application_0a=" + FAKE_HEX),
                          ("c/x.cfg", "MASTER_KEY" + "_00 = " + FAKE_HEX.upper()),
                          ("d/title.txt", FAKE_HEX + " = " + FAKE_HEX)):
            with self.subTest(rel=rel):
                self.put(rel, "# fake\n" + line + "\n")
                self.assert_refused(rel)
                (self.root / rel).unlink()

    def test_pem_private_keys_including_encrypted(self):
        for kind in ("", "RSA ", "ENCRYPTED ", "OPENSSH "):
            with self.subTest(kind=kind):
                self.put("k.txt", "-----BEGIN " + kind + "PRIVATE KEY-----\nAAAA\n")
                self.assert_refused("k.txt")

    def test_literal_keystore_passwords(self):
        cases = {
            "app/signing.gradle": STORE + ' "fake-secret"\n',
            "app/build.gradle.kts": "key" + 'Password = "fake-secret"\n',
            "keystore.properties": STORE + "=fake-secret\n",
            "sign.sh": "keytool -genkeypair -store" + "pass fake-secret -alias a\n",
            "sign.py": "cmd = ['-store" + "pass', 'fake-secret']\n",
            "apk.sh": "apksigner sign --ks-" + "pass pass:fake-secret app.apk\n",
        }
        for rel, text in cases.items():
            with self.subTest(rel=rel):
                self.put(rel, text)
                r = self.assert_refused(rel)
                self.assertNotIn("fake-secret", r.stderr)  # the value is never printed
                (self.root / rel).unlink()

    def test_passwords_from_the_environment_or_public_pass(self):
        self.put("app/build.gradle.kts",
                 STORE + ' = providers.environmentVariable("PASS").get()\n'
                 "key" + "Password = " + STORE + "\n"
                 + STORE + ' "${System.getenv("PASS")}"\n')
        self.put("ci.yml", "keytool -list -store" + "pass:env KS_PASS\n"
                 "apksigner sign --ks-" + "pass env:KS_PASS --key-" + "pass env:KEY_PASS\n"
                 'keytool -store' + 'pass "${ANDROID_KEYSTORE_PASS}"\n')
        self.put("debug.py", "['-store" + "pass', 'android', '-key" + "pass', 'android']\n")
        self.put("ci.sh", "keytool -store" + "pass ci-only -key" + "pass ci-only\n")
        self.put("gradle.properties", "org.gradle.jvmargs=-Xmx2g\n" + STORE + "=$KS_PASS\n")
        self.assert_clean()

    def test_git_tree_scans_what_could_be_committed(self):
        git(self.root, "init", "-q")
        self.put(".gitignore", "/private/\n")
        secret = "TOKEN=" + "ghp" + "_" + "B" * 36 + "\n"
        self.put("private/ci.env", secret)
        self.assert_clean()  # ignored and untracked: cannot reach a commit
        git(self.root, "add", "-f", "private/ci.env")
        self.assert_refused("private/ci.env")  # a forced add does not get through

    def test_history_covers_every_commit(self):
        # The secret lives only in the first of 202 commits: the old 200-commit limit
        # would have missed it.
        git(self.root, "init", "-q")
        self.put("old.txt", "TOKEN=" + "ghp" + "_" + "C" * 36 + "\n")
        git(self.root, "add", "old.txt")
        git(self.root, "commit", "-q", "-m", "leak")
        git(self.root, "rm", "-q", "old.txt")
        git(self.root, "commit", "-q", "--allow-empty", "-m", "remove")
        for i in range(200):
            git(self.root, "commit", "-q", "--allow-empty", "-m", f"c{i}")
        self.assert_clean()  # the tree itself is clean
        r = self.assert_refused("old.txt", "--history")
        leak = subprocess.run(["git", "-C", str(self.root), "rev-list", "--max-parents=0",
                               "--abbrev-commit", "HEAD"], capture_output=True, text=True)
        self.assertIn(leak.stdout.strip(), r.stderr)  # names the commit that added it

    def test_history_outside_git_is_an_error(self):
        r = run_scanner(self.root, "--history")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
