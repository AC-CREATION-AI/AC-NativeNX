"""Synthetic regression cases: never use real credentials or game data."""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GuardHardeningTests(unittest.TestCase):
    def test_disguised_and_switch_paths(self):
        guard = load('check_letsgo_content')
        for name in ['PROD.KEYS.txt', 'payload.nso', 'payload.nro', 'payload.npdm',
                     'romfs.bin', 'private/signing.jks', 'save/state', 'mods/data',
                     'extracted/data']:
            with self.subTest(name=name):
                self.assertTrue(guard.reason_for(ROOT / name))

    def test_key_contents_without_filename_hint(self):
        guard = load('check_no_secrets')
        cases = [prefix + ' = ' + 'a' * 32 for prefix in
                 ['header_key', 'key_area_key_application_00', 'titlekek_00', 'master_key_00']]
        cases += ['-----BEGIN ' + 'ENCRYPTED PRIVATE KEY-----',
                  'storePassword ' + '"synthetic-only"',
                  'keyPassword=' + 'synthetic-only']
        for text in cases:
            findings = []
            guard.scan_bytes(text.encode(), 'synthetic.ini', findings)
            self.assertTrue(findings, text.split('=')[0])

    def test_environment_signing_is_not_a_literal(self):
        guard = load('check_no_secrets')
        for text in [
            'storePassword = providers.environmentVariable("SIGNING_PASSWORD").get()',
            'keyPassword = storePassword',
            'storePassword=<value>',
        ]:
            findings = []
            guard.scan_bytes(text.encode(), 'synthetic.gradle.kts', findings)
            self.assertEqual(findings, [])
        for text in ['storePassword = "synthetic-only"',
                     'keyPassword = synthetic-only',
                     'keyPassword = storePassword + "synthetic-only"']:
            findings = []
            guard.scan_bytes(text.encode(), 'synthetic.gradle.kts', findings)
            self.assertTrue(findings)

    def test_diagnostics_do_not_echo_credentials(self):
        guard = load('check_no_secrets')
        findings = []
        value = b'a' * 32
        guard.scan_bytes(b'header_key = ' + value, 'synthetic.ini', findings)
        self.assertTrue(findings)
        self.assertNotIn(value.decode(), repr(findings))


if __name__ == '__main__':
    unittest.main()
