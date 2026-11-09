"""Synthetic launcher preflight tests; no upstream sources or compiler needed."""
import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'tools/run_host_checks.py'
spec = importlib.util.spec_from_file_location('host_checks', SCRIPT)
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)

INPUTS = (
    'sources/las-android/runtime/nvn/shader_prep.h',
    'sources/las-android/runtime/ipc.h',
    'work/shared-android/third_party/imgui/imgui.cpp',
)


class PreconditionsTest(unittest.TestCase):
    def invoke(self, root, android=False):
        err = io.StringIO()
        argv = ['run_host_checks.py', '--report', str(root / 'report.json')]
        if android:
            argv.append('--android')
        with patch.object(host, 'ROOT', root), patch.object(host, 'CHECKS', []), \
                patch.object(host.sys, 'argv', argv), \
                patch.object(host.subprocess, 'run') as run, \
                contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            try:
                rc = host.main()
            except SystemExit as exc:
                rc = exc.code
            run.assert_not_called()
        return rc, err.getvalue()

    def test_each_missing_input_fails_before_checks(self):
        for absent in (None, *INPUTS):
            with self.subTest(absent=absent), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                for name in INPUTS:
                    if absent is not None and name != absent:
                        path = root / name
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text('// synthetic\n')
                rc, error = self.invoke(root)
                self.assertEqual(rc, 2)
                for name in INPUTS if absent is None else (absent,):
                    self.assertIn(name, error)
                self.assertIn('python3 tools/fetch_sources.py', error)
                self.assertIn('python3 tools/build_shared_android.py', error)
                self.assertIn('engine/', error)
                self.assertFalse((root / 'report.json').exists())

    def test_prepared_host_needs_no_android_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in INPUTS:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('// synthetic\n')
            self.assertEqual(self.invoke(root), (0, ''))
            rc, error = self.invoke(root, android=True)
            self.assertEqual(rc, 2)
            self.assertIn('build_shared_android.py --build', error)


if __name__ == '__main__':
    unittest.main()
