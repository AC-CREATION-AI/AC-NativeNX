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
            extra = tree / 'restored/src/android/app/src/main/res/values/qa_extra.xml'
            extra.write_text('<resources/>')
            result = subprocess.run([sys.executable, 'tools/build_eden_shell.py', '--shell', '../restored',
                                     '--unsigned', '--build', '--jobs', '2'],
                                    cwd=engine, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Archive shell differs:', result.stderr)
            self.assertIn('qa_extra.xml', result.stderr)
            self.assertNotIn('native-build.json', result.stderr)
            self.assertFalse((engine / 'build/eden-shell/build.log').exists())
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


class ShellBuildBoundary(unittest.TestCase):
    def test_archive_shell_inventory_before_native_or_gradle(self):
        import build_eden_shell as builder
        import json
        import os
        import shutil
        from unittest.mock import patch

        cases = ('clean', 'extra', 'missing', 'modified', 'file_link',
                 'directory_link', 'broken_extra_link', 'changed_link',
                 'link_as_file', 'fifo', 'outputs', 'nested_build', 'output_link')
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                expected, restored = root / 'expected', root / 'restored'
                resource = 'src/android/app/src/main/res/values/base.xml'
                extra = 'src/android/app/src/main/res/values/qa_extra.xml'
                (expected / resource).parent.mkdir(parents=True)
                (expected / resource).write_text('locked')
                (expected / 'src/android/raitchi-build').mkdir()
                (expected / 'link').symlink_to(resource)
                shutil.copytree(expected, restored, symlinks=True)
                if case == 'extra':
                    (restored / extra).write_text('unexpected')
                elif case == 'missing':
                    (restored / resource).unlink()
                elif case == 'modified':
                    (restored / resource).write_text('changed')
                elif case == 'file_link':
                    (restored / resource).unlink()
                    (restored / resource).symlink_to(expected / resource)
                elif case == 'directory_link':
                    shutil.rmtree(restored / 'src/android/app')
                    (restored / 'src/android/app').symlink_to(expected / 'src/android/app')
                elif case == 'broken_extra_link':
                    (restored / 'extra').symlink_to('missing')
                elif case == 'changed_link':
                    (restored / 'link').unlink()
                    (restored / 'link').symlink_to('missing')
                elif case == 'link_as_file':
                    (restored / 'link').unlink()
                    (restored / 'link').write_text('locked')
                elif case == 'fifo':
                    os.mkfifo(restored / 'extra')
                elif case == 'outputs':
                    for name in ('src/android/.gradle/cache',
                                 'src/android/raitchi-build/.gradle/cache',
                                 'src/android/local.properties'):
                        path = restored / name
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text('generated')
                elif case == 'nested_build':
                    path = restored / 'src/android/app/src/main/build/extra.xml'
                    path.parent.mkdir(parents=True)
                    path.write_text('not an output')
                elif case == 'output_link':
                    (restored / 'src/android/.gradle').symlink_to(expected, target_is_directory=True)
                lock = {'path': 'unused', 'commit': 'a' * 40}
                (root / 'shell.lock.json').write_text(json.dumps(lock))
                (root / 'shell-overlay.json').write_text(json.dumps({
                    'upstream_commit': 'a' * 40, 'deleted_upstream_files': []}))

                def reconstruct(command, **kwargs):
                    shutil.copytree(expected, Path(command[-1]), symlinks=True)

                # No actual native receipt or Gradle is available: reaching this boundary
                # is the clean-tree success sentinel, never a successful Android build.
                with patch.object(builder, 'ROOT', root / 'engine'), \
                     patch.object(builder, 'BUILD', root / 'build'), \
                     patch.object(builder, 'SHELL_LOCK', root / 'shell.lock.json'), \
                     patch.object(builder, 'run', side_effect=reconstruct) as run, \
                     patch.object(builder.engine, 'verify_native',
                                  side_effect=RuntimeError('native-build.json sentinel')) as native, \
                     patch.object(sys, 'argv', ['build_eden_shell.py', '--shell', str(restored),
                                               '--sdk', str(root), '--unsigned', '--build', '--jobs', '2']):
                    if case in ('clean', 'outputs'):
                        with self.assertRaisesRegex(RuntimeError, 'native-build.json sentinel'):
                            builder.main()
                        native.assert_called_once()
                    else:
                        with self.assertRaisesRegex(RuntimeError, 'Archive shell differs'):
                            builder.main()
                        native.assert_not_called()
                    self.assertEqual(run.call_count, 1)  # reconstruction only, never Gradle
