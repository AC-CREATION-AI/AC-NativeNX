"""Synthetic checks of the Git-free, locked source staging boundary."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1] / 'engine/tools'
import sys
sys.path.insert(0, str(TOOLS))


class ArchiveStaging(unittest.TestCase):
    def test_verified_stage_never_copies_untracked_extras(self):
        spec = importlib.util.spec_from_file_location('archive_sources', TOOLS / 'archive_sources.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        import io
        import tarfile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / 'upstream.tar.gz'
            with tarfile.open(archive, 'w:gz') as stream:
                member = tarfile.TarInfo('upstream/file.txt')
                member.size = 6
                stream.addfile(member, io.BytesIO(b'pinned'))
            destination = root / 'stage'
            module.extract(archive, destination)
            self.assertEqual((destination / 'file.txt').read_bytes(), b'pinned')
            self.assertFalse((destination / '.git').exists())

    def test_archive_cannot_write_outside_stage(self):
        spec = importlib.util.spec_from_file_location('archive_sources', TOOLS / 'archive_sources.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        import io
        import tarfile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / 'bad.tar.gz'
            with tarfile.open(archive, 'w:gz') as stream:
                member = tarfile.TarInfo('upstream/../../escape')
                member.size = 1
                stream.addfile(member, io.BytesIO(b'x'))
            with self.assertRaises(ValueError):
                module.extract(archive, root / 'stage')
            self.assertFalse((root / 'escape').exists())
