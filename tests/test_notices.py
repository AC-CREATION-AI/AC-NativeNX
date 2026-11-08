#!/usr/bin/env python3
"""Licence notices: in the repository, in the packaged assets and in the built APK (no build, no game data).

Run: python3 -m unittest tests.test_notices -v
"""
import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine/tools"))
import build_eden_shell  # noqa: E402
import package_shared_android  # noqa: E402

RYUJINX = ROOT / "LICENSES/Ryujinx-MIT.txt"
# Software Heritage swh:1:cnt:818ddd76058d49f42eed9c0ecb580777c7f87d7e (Ryujinx/Ryujinx LICENSE.txt, master
# cd74ae1bbd49), the same file as letsgo-recomp-android's LICENSES/Ryujinx-MIT.txt.
RYUJINX_SHA256 = "781bbdf040b7d0286c47cca6bffdb9148dfe751c0c9cabdf1a1752412a2e56b4"
# The canonical GPLv3 text published by the FSF (https://www.gnu.org/licenses/gpl-3.0.txt), = shell/LICENSE.txt.
CANONICAL_GPL3_SHA256 = "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RepositoryNotices(unittest.TestCase):
    def test_ryujinx_licence_text_is_the_archived_one(self):
        self.assertEqual(sha(RYUJINX), RYUJINX_SHA256)

    def test_ryujinx_is_mapped_in_license_and_notice(self):
        for name in ("LICENSE", "NOTICE.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn("LICENSES/Ryujinx-MIT.txt", text, name)
            self.assertIn("Ryujinx", text, name)

    def test_ryujinx_derived_sources_point_to_an_existing_licence(self):
        audio = (ROOT / "engine/ports/shared-android/runtime/services/audio.c").read_text(encoding="utf-8")
        self.assertNotIn("third_party/ryujinx/LICENSE.txt", audio)  # never existed in this repository
        self.assertIn("LICENSES/Ryujinx-MIT.txt", audio)

    def test_copying_is_the_canonical_gpl3_text(self):
        self.assertEqual(sha(ROOT / "shell/LICENSE.txt"), CANONICAL_GPL3_SHA256)
        self.assertEqual(sha(ROOT / "COPYING"), CANONICAL_GPL3_SHA256)
        self.assertEqual(sha(ROOT / "engine/COPYING"), CANONICAL_GPL3_SHA256)

    def test_license_map_title(self):
        first = (ROOT / "LICENSE").read_text(encoding="utf-8").splitlines()[0]
        self.assertEqual(first, "AC-NativeNX license map (from Raitchi)")


class PackagedNotices(unittest.TestCase):
    def test_every_engine_notice_is_packaged(self):
        assets = package_shared_android.notice_assets(Path("/las-source"))
        self.assertEqual(assets["LICENSE-Ryujinx.txt"], RYUJINX)
        for name, path in assets.items():
            if not str(path).startswith("/las-source"):
                self.assertTrue(path.is_file(), f"{name}: {path} is missing")

    def test_apk_inventory_lists_the_notices(self):
        required = set(package_shared_android.notice_assets(Path("/las-source")))
        names = ["classes.dex", "lib/arm64-v8a/libmain.so", "assets/GPL-3.0-or-later.txt", "assets/MIT.txt",
                 "assets/DejaVuSans.ttf"] + ["assets/" + n for n in required]
        inventory = build_eden_shell.notice_inventory(names, required, {"GPL-3.0-or-later.txt", "MIT.txt"})
        self.assertIn("LICENSE-Ryujinx.txt", inventory)
        self.assertIn("GPL-3.0-or-later.txt", inventory)
        self.assertNotIn("DejaVuSans.ttf", inventory)

    def test_apk_without_a_required_notice_is_refused(self):
        required = set(package_shared_android.notice_assets(Path("/las-source")))
        names = ["assets/GPL-3.0-or-later.txt"] + ["assets/" + n for n in required if n != "LICENSE-Ryujinx.txt"]
        with self.assertRaisesRegex(RuntimeError, r"APK_NOTICES_MISSING: .*LICENSE-Ryujinx\.txt"):
            build_eden_shell.notice_inventory(names, required, {"GPL-3.0-or-later.txt"})
        with self.assertRaisesRegex(RuntimeError, r"APK_NOTICES_MISSING: .*GPL-3\.0-or-later\.txt"):
            build_eden_shell.notice_inventory(["assets/" + n for n in required], required, {"GPL-3.0-or-later.txt"})


if __name__ == "__main__":
    unittest.main()
