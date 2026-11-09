"""The public repository names no private network address and no internal host path."""
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = re.compile(
    r"\b(?:10\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])|192\.168)\.\d{1,3}\.\d{1,3}\b"  # RFC 1918 addresses
    r"|/opt" r"/data/"  # internal agent host layout (split so this line does not match itself)
)
SKIP = ("src/third_party/",)  # vendored upstream code


class NoInternalInfraTest(unittest.TestCase):
    def test_tracked_files_name_no_internal_infrastructure(self):
        files = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
        found = []
        for name in filter(None, files.decode().split("\0")):
            path = ROOT / name
            if name.startswith(SKIP) or not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue  # binary
            for n, line in enumerate(text.splitlines(), 1):
                if PRIVATE.search(line):
                    found.append(f"{name}:{n}: internal infrastructure (content omitted)")
        self.assertEqual(found, [], "internal address or path in a public file:\n" + "\n".join(found))


if __name__ == "__main__":
    unittest.main()
