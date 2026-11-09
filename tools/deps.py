#!/usr/bin/env python3
"""deps.lock reader: fetch and verify the pinned third-party inputs, check them against the build, make the
corresponding source archive. Model: letsgo-recomp-android's tools/ci/deps.py.

  deps.py list                       kind, name, version, license of every entry
  deps.py fetch [--dir D] [--offline]
                                     download (or, --offline, only check) every `dep` into D (default
                                     $NATIVENX_DEPS_DL or deps/dl) and check its sha256; exit 1 on any mismatch
  deps.py check [--dir D]            deps.lock agrees with the build: source locks, shell lock, cpmfile.json,
                                     build_letsgo_ffmpeg.py, prepare_shared_ondevice.py and, when the pinned
                                     sources are present (engine/sources/las-android, fetched shaderc archive),
                                     LAS build_deps.sh, LAS CMakeLists.txt and shaderc's DEPS
  deps.py source-tarball OUT VERSION [--dir D]
                                     OUT = AC-NativeNX-<VERSION>-source.tar.gz: `git archive HEAD` + every
                                     "in source tarball = yes" archive under deps/dl/ + SOURCE-README.md;
                                     exit 1 if one is missing or is not the pinned file

Standard library only. Downloaded archives are data: read with tarfile, never executed or extracted here.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "deps.lock"
ENGINE = ROOT / "engine"
KINDS = ("dep", "unused", "cpm")


def parse(lock=LOCK):
    entries = {kind: {} for kind in KINDS}
    for n, line in enumerate(Path(lock).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        f = [x.strip() for x in line.split("|")]
        if f[0] not in KINDS:
            sys.exit(f"deps.lock:{n}: unknown kind {f[0]!r}")
        if len(f) != 7:
            sys.exit(f"deps.lock:{n}: {f[0]} needs 7 fields, has {len(f)}")
        if f[1] in entries[f[0]]:
            sys.exit(f"deps.lock:{n}: duplicate {f[0]} {f[1]}")
        entries[f[0]][f[1]] = dict(kind=f[0], name=f[1], version=f[2], license=f[3], source=f[4], sha256=f[5],
                                   url=f[6], line=n)
    return entries


def filename(e):
    """Local file name: the URL's last path element, prefixed with the name for /archive/<ref> URLs."""
    base = e["url"].rstrip("/").rsplit("/", 1)[-1]
    if "/archive/" in e["url"]:
        base = e["name"] + "-" + base
    return base


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def dl_dir(args):
    return Path(args.dir or os.environ.get("NATIVENX_DEPS_DL") or ROOT / "deps/dl")


def fetch(args):
    deps = parse()["dep"]
    d = dl_dir(args)
    d.mkdir(parents=True, exist_ok=True)
    bad = 0
    for name, e in deps.items():
        p = d / filename(e)
        if not p.is_file():
            if args.offline:
                print(f"MISSING {name}: {p}")
                bad += 1
                continue
            if not e["url"].startswith("https://"):
                sys.exit(f"{name}: not an https URL")
            tmp = p.with_suffix(p.suffix + ".part")
            for attempt in range(4):
                try:
                    req = urllib.request.Request(e["url"], headers={"User-Agent": "ac-nativenx-deps/1"})
                    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as out:
                        while b := r.read(1 << 20):
                            out.write(b)
                    break
                except OSError as err:
                    if attempt == 3:
                        sys.exit(f"{name}: download failed: {err}")
                    time.sleep(5 * (attempt + 1))
            os.replace(tmp, p)
        got = sha256(p)
        if got != e["sha256"]:
            print(f"SHA256_MISMATCH {name}: {p} is {got}, deps.lock says {e['sha256']}")
            bad += 1
        else:
            print(f"OK {name} {e['version']} {p.name}")
    if bad:
        sys.exit(f"{bad} dependency check(s) failed")


def consistency(dl, las=ENGINE / "sources/las-android"):
    """Every disagreement between deps.lock and what the build really uses, as a list of messages."""
    entries = parse()
    deps, unused, cpm = entries["dep"], entries["unused"], entries["cpm"]
    problems = []

    def expect(name, version=None, sha=None, url=None, where=""):
        e = deps.get(name)
        if e is None:
            problems.append(f"{where}: {name} is not a `dep` of deps.lock")
            return
        for field, want in (("version", version), ("sha256", sha), ("url", url)):
            if want is not None and e[field] != want:
                problems.append(f"{where}: {name} {field} is {want}, deps.lock says {e[field]}")

    for lock in ("sources.lock.json", "echoes-source.lock.json"):
        for s in json.loads((ENGINE / lock).read_text(encoding="utf-8"))["sources"]:
            repo = s["url"].removesuffix(".git")
            expect(s["id"], s["commit"], url=f"{repo}/archive/{s['commit']}.tar.gz", where="engine/" + lock)
    shell = json.loads((ENGINE / "shell.lock.json").read_text(encoding="utf-8"))["upstream"]
    expect("eden", shell["commit"], url=f"{shell['url']}/archive/{shell['commit']}.tar.gz",
           where="engine/shell.lock.json")
    overlay = json.loads((ROOT / "shell-overlay.json").read_text(encoding="utf-8"))
    expect("eden", overlay["upstream_commit"], where="shell-overlay.json")

    ffmpeg = (ENGINE / "tools/build_letsgo_ffmpeg.py").read_text(encoding="utf-8")
    m = re.search(r'ARCHIVE_SHA = "([0-9a-f]{64})"', ffmpeg)
    expect("ffmpeg", sha=m and m.group(1), where="engine/tools/build_letsgo_ffmpeg.py")
    ondevice = (ENGINE / "tools/prepare_shared_ondevice.py").read_text(encoding="utf-8")
    m = re.search(r'"capstone-dl/capstone-([0-9.]+)\.tar\.gz", "([^"]+)", "([0-9a-f]{64})"', ondevice)
    if m:
        expect("capstone", m.group(1), m.group(3), m.group(2), where="engine/tools/prepare_shared_ondevice.py")
    else:
        problems.append("engine/tools/prepare_shared_ondevice.py: capstone input not found")

    cpmfile = json.loads((ROOT / "shell/cpmfile.json").read_text(encoding="utf-8"))
    if set(cpmfile) != set(cpm):
        problems.append(f"shell/cpmfile.json and the `cpm` lines differ: {sorted(set(cpmfile) ^ set(cpm))}")
    for name, v in cpmfile.items():
        version = v["version"].replace("%NUMERIC_VERSION%", v.get("numeric_version", ""))
        if name in cpm and cpm[name]["version"] != version:
            problems.append(f"shell/cpmfile.json: {name} version is {version}, deps.lock says {cpm[name]['version']}")

    build_deps = las / "tools/android/build_deps.sh"
    if build_deps.is_file():
        text = build_deps.read_text(encoding="utf-8").replace("$TURNIP", "turnip_v24.3.0_R9v2.zip")
        fetched = re.findall(r"fetch (https://\S+) \\?\s*\n?\s*([0-9a-f]{64})", text)
        if len(fetched) < 6:
            problems.append(f"{build_deps}: expected at least 6 pinned downloads, found {len(fetched)}")
        known = {(e["url"], e["sha256"]) for e in list(deps.values()) + list(unused.values())}
        for url, sha in fetched:
            if (url, sha) not in known:
                problems.append(f"LAS build_deps.sh downloads {url} ({sha[:12]}), not in deps.lock")
        cmake = (las / "android/app/CMakeLists.txt").read_text(encoding="utf-8")
        m = re.search(r"libadrenotools\.git\s+GIT_TAG ([0-9a-f]{40})", cmake)
        expect("libadrenotools", m and m.group(1), where="LAS android/app/CMakeLists.txt")
    shaderc = dl / filename(deps["shaderc"]) if "shaderc" in deps else None
    if shaderc and shaderc.is_file() and sha256(shaderc) == deps["shaderc"]["sha256"]:
        with tarfile.open(shaderc) as t:
            member = next(m for m in t.getmembers() if m.name.endswith("/DEPS") and m.name.count("/") == 1)
            text = t.extractfile(member).read().decode()
        for var, name in (("glslang_revision", "glslang"), ("spirv_tools_revision", "spirv-tools"),
                          ("spirv_headers_revision", "spirv-headers")):
            m = re.search(rf"'{var}':\s*'([0-9a-f]{{40}})'", text)
            expect(name, m and m.group(1), where="shaderc DEPS")
        for var, name in (("abseil_revision", "abseil-cpp"), ("effcee_revision", "effcee"),
                          ("googletest_revision", "googletest"), ("re2_revision", "re2")):
            m = re.search(rf"'{var}':\s*'([0-9a-f]{{40}})'", text)
            if not m or name not in unused or unused[name]["version"] != m.group(1):
                problems.append(f"shaderc DEPS: {name} {m and m.group(1)} is not an `unused` line of deps.lock")
    return problems


def check(args):
    problems = consistency(dl_dir(args))
    for p in problems:
        print("DEPS_LOCK_STALE " + p)
    if problems:
        sys.exit(f"{len(problems)} disagreement(s) between deps.lock and the build")
    las = (ENGINE / "sources/las-android/tools/android/build_deps.sh").is_file()
    print("DEPS_LOCK_OK" + ("" if las else " (LAS build_deps.sh not fetched: its downloads were not compared)"))


def source_tarball(args):
    entries = parse()
    deps = entries["dep"]
    d = dl_dir(args)
    out = Path(args.out).resolve()
    top = f"AC-NativeNX-{args.version}"
    shipped = [e for e in deps.values() if e["source"] == "yes"]
    missing = [e["name"] for e in shipped if not (d / filename(e)).is_file() or sha256(d / filename(e)) != e["sha256"]]
    if missing:
        sys.exit("SOURCE_ARCHIVE_MISSING: " + ", ".join(missing) + f" (not in {d} or not the pinned file; "
                 "run tools/deps.py fetch)")
    readme = [f"# {top} - corresponding source", "",
              "This archive is the complete corresponding source of the APK published with it:", "",
              f"- `{top}/` is this repository at the built commit (`git archive`), with the build scripts",
              "  (`engine/tools/*.py`, `tools/deps.py`, `.github/workflows/build.yml`) and the hashed Eden shell",
              "  overlay (`shell/`, `shell-overlay.json`) that produced it;",
              f"- `{top}/deps/dl/` holds the unmodified upstream archives of everything else the APK is built",
              "  from (sha256 pinned in `deps.lock`):", ""]
    for e in shipped:
        readme.append(f"  - `{filename(e)}`: {e['name']} {e['version']} ({e['license']}), from {e['url']}")
    readme += ["", "Downloaded by a build script but not in the APK (`unused` in `deps.lock`):", ""]
    readme += [f"- {e['name']} {e['version']} ({e['license']}): {e['url']}" for e in entries["unused"].values()]
    readme += ["", "The shell/cpmfile.json packages (`cpm` in `deps.lock`) are not built for Android: Eden's C++ core",
               "is not compiled and the APK carries only the engine's native libraries.", "",
               "Rebuild (Linux x86_64, JDK 17, Android SDK/NDK r27c, see engine/docs/BUILDING.md and",
               "`.github/workflows/build.yml`): unpack the pinned repositories where `engine/tools/fetch_sources.py`",
               "and `engine/tools/restore_shell_overlay.py` would clone them, or let them fetch the same commits;",
               "the archives under deps/dl/ are the exact files the build downloads.", "",
               "## Verify the pinned sources without Git", "",
               "This archive has no `.git` directory. From its top directory, unpack each pinned repository at the",
               "path of its source lock (`engine/sources.lock.json`, `engine/echoes-source.lock.json`), then verify:",
               "", "```sh"]
    for lock in ("sources.lock.json", "echoes-source.lock.json"):
        for s in json.loads((ENGINE / lock).read_text(encoding="utf-8"))["sources"]:
            readme += [f"mkdir -p engine/{s['path']} && tar -xzf deps/dl/{filename(deps[s['id']])} "
                       f"-C engine/{s['path']} --strip-components=1"]
    readme += ["cd engine",
               "python3 tools/verify_sources.py --archives",
               "python3 tools/verify_sources.py --archives --lock echoes-source.lock.json", "```", "",
               "`--archives` checks each archive's sha256 against `deps.lock`, the `deps.lock` entry against the",
               "source lock's commit and URL, and every archived file against the unpacked tree (exit 0 = OK).",
               "All stages below consume these locked archives without creating Git history. Use at most two jobs.",
               "The host toolchain must be on PATH; SDK defaults to $HOME/android-sdk. No device is used.",
               "", "```sh",
               "python3 tools/build_las_baseline.py --deps --jobs 2",
               "python3 tools/build_las_baseline.py --native-only --jobs 2",
               "python3 tools/build_letsgo_ffmpeg.py --build --jobs 2",
               "python3 tools/prepare_shared_ondevice.py --fetch --build --jobs 2",
               "# On the first run, final toolkit metadata may require libmain.so; Capstone must exist:",
               "test -f build/shared-ondevice/stage/jniLibs/arm64-v8a/libcapstone.so",
               "python3 tools/build_shared_android.py --build --jobs 2",
               "python3 tools/restore_shell_overlay.py --archives --snapshot ../shell --manifest ../shell-overlay.json --destination ../shell-restored",
               "python3 tools/build_eden_shell.py --shell ../shell-restored --build --allow-downloads --variant release --unsigned --jobs 2",
               "```", "", "The final APK is engine/build/eden-shell/raitchi-eden-app-release.apk (unsigned).", ""]
    git = subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar", f"--prefix={top}/", "HEAD"],
                         check=True, capture_output=True).stdout
    mtime = int(subprocess.run(["git", "-C", str(ROOT), "log", "-1", "--format=%ct"], check=True,
                               capture_output=True, text=True).stdout.strip())

    def info(name, size):
        ti = tarfile.TarInfo(name)
        ti.size, ti.mtime, ti.mode, ti.uid, ti.gid, ti.uname, ti.gname = size, mtime, 0o644, 0, 0, "", ""
        return ti

    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=out.parent, delete=False) as tmp:
        with tarfile.open(fileobj=tmp, mode="w:gz", format=tarfile.PAX_FORMAT) as t:
            with tarfile.open(fileobj=io.BytesIO(git)) as g:
                for m in g.getmembers():
                    t.addfile(m, g.extractfile(m) if m.isfile() else None)
            body = "\n".join(readme).encode()
            t.addfile(info(f"{top}/SOURCE-README.md", len(body)), io.BytesIO(body))
            for e in shipped:
                p = d / filename(e)
                with open(p, "rb") as f:
                    t.addfile(info(f"{top}/deps/dl/{p.name}", p.stat().st_size), f)
    os.replace(tmp.name, out)
    print(f"SOURCE_TARBALL_OK {out} {sha256(out)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    f = sub.add_parser("fetch")
    f.add_argument("--dir")
    f.add_argument("--offline", action="store_true")
    c = sub.add_parser("check")
    c.add_argument("--dir")
    s = sub.add_parser("source-tarball")
    s.add_argument("out")
    s.add_argument("version")
    s.add_argument("--dir")
    args = ap.parse_args()
    if args.cmd == "list":
        for kind, entries in parse().items():
            for e in entries.values():
                print(f"{kind}\t{e['name']}\t{e['version']}\t{e['license']}")
    elif args.cmd == "fetch":
        fetch(args)
    elif args.cmd == "check":
        check(args)
    else:
        source_tarball(args)


if __name__ == "__main__":
    main()
