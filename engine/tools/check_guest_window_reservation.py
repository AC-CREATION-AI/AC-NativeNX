#!/usr/bin/env python3
"""Guest window reservation strategy against simulated 39-bit VA collisions; no games/device."""
import hashlib, json, shutil, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    out = ROOT / 'build/guest-window-reservation'
    out.mkdir(parents=True, exist_ok=True)
    sources = [ROOT / x for x in (
        'native/module_abi.c', 'native/runtime/native_manifest.c', 'native/runtime/session_layout.c',
        'native/adapters/title_adapter.c', 'native/adapters/las/profile.c', 'native/adapters/letsgo/profile.c',
        'native/adapters/echoes/profile.c', 'native/adapters/wonder/profile.c')]
    test = ROOT / 'tests/guest_window_reservation_test.c'
    paths = sources + [ROOT / 'native/adapters/title_adapter.h', ROOT / 'native/runtime/native_manifest.h',
                       ROOT / 'native/runtime/aot_cpu.h', test, Path(__file__).resolve()]
    pins = {str(p.relative_to(ROOT)): sha(p) for p in paths}

    def run(args, log):
        r = subprocess.run(list(map(str, args)), capture_output=True, text=True, timeout=120)
        (out / log).write_text(r.stdout + r.stderr)
        if r.returncode:
            raise RuntimeError(log + ': ' + r.stdout + r.stderr)
        return r.stdout

    common = ['-std=c11', '-D_GNU_SOURCE', '-Wall', '-Wextra', '-Werror', '-I', ROOT / 'native']
    reports = {}
    for mode, flags in [('optimized', ['-O2']),
                        ('sanitized', ['-O1', '-g', '-fsanitize=address,undefined', '-fno-omit-frame-pointer'])]:
        binary = out / ('guest-window-reservation-' + mode)
        run([shutil.which('clang'), *common, *flags, *sources, test, '-pthread', '-o', binary], mode + '-build.log')
        for title in ('las', 'eevee'):
            stdout = run([binary, title], mode + '-' + title + '.log')
            reports[mode + '-' + title] = {'passed': True, 'stdout': stdout.strip()}
    assert pins == {str(p.relative_to(ROOT)): sha(p) for p in paths}, 'Source changed during verification'
    result = {'schema': 1, 'state': 'passed', 'host': reports, 'source_sha256': pins,
              'scope': 'Real title_adapter/session_layout contract with synthetic native manifests; Fold4-style '
                       'collision simulation (mapping inside the canonical window) and no-clobber proof via '
                       'MAP_FIXED_NOREPLACE over the effective window; sanitized build runs logic only '
                       '(address scenarios not executed: ASan shadow owns the fixed addresses). No device, '
                       'game files or original code.'}
    (out / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
