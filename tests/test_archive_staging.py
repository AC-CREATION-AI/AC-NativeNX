"""Synthetic checks of the Git-free, locked source staging boundary."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1] / 'engine/tools'
import sys
sys.path.insert(0, str(TOOLS))


class ArchiveStaging(unittest.TestCase):
    def test_real_distribution_stages_without_git(self):
        import os
        import subprocess
        root = Path(__file__).resolve().parents[1]
        if not (root / 'deps/dl').is_dir():
            self.skipTest('pinned archives unavailable; run tools/deps.py fetch')
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / 'source.tar.gz'
            subprocess.run([sys.executable, root / 'tools/deps.py', 'source-tarball', archive, 'test'], check=True, capture_output=True)
            import tarfile
            with tarfile.open(archive) as stream:
                stream.extractall(directory, filter='data')
            tree = Path(directory) / 'AC-NativeNX-test'
            readme = (tree / 'SOURCE-README.md').read_text()
            subprocess.run(['bash', '-e', '-c', readme.split('```sh')[1].split('```')[0]], cwd=tree, check=True, capture_output=True)
            engine = tree / 'engine'
            for command in (
                ['tools/prepare_shared_ondevice.py'],
                ['tools/build_shared_android.py'],
                ['tools/build_las_baseline.py'],
                ['tools/restore_shell_overlay.py', '--archives', '--snapshot', '../shell', '--manifest', '../shell-overlay.json', '--destination', '../restored'],
            ):
                subprocess.run([sys.executable, *command], cwd=engine, check=True, capture_output=True)
            result = subprocess.run([sys.executable, 'tools/build_eden_shell.py', '--shell', '../restored', '--unsigned'], cwd=engine, capture_output=True, text=True)
            # Native compilation is deliberately not part of this lightweight staging test.
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('native-build.json', result.stderr)
            self.assertNotIn('not a git repository', result.stderr)
            self.assertFalse(list(tree.rglob('.git')))
            # Unpacked tree integrity remains mandatory at every staging entry point.
            victim = engine / 'sources/las-android/README.md'
            victim.write_text('tampered')
            result = subprocess.run([sys.executable, 'tools/build_shared_android.py'], cwd=engine, capture_output=True)
            self.assertNotEqual(result.returncode, 0)

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
