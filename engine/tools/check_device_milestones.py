#!/usr/bin/env python3
"""Device-run milestones (docs/DEVICE-MILESTONES.md): each marker is still written where it should be, and the native
helper prints the expected line. Host only: no device, GPU, game or key."""
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build/device-milestones"
RUNTIME = ROOT / "ports/shared-android/runtime"
MAIN_ACTIVITY = ROOT.parent / "shell/src/android/app/src/main/java/org/yuzu/yuzu_emu/ui/main/MainActivity.kt"

# marker -> (file, text that must surround it there)
SITES = {
    "APP_OPEN": (MAIN_ACTIVITY, r'super\.onCreate\(savedInstanceState\)\s*\n(?:\s*//.*\n)?\s*android\.util\.Log\.i\("ACMilestone",'),
    "MEM_RESERVE_FAIL": (RUNTIME / "gamelib.c", r'if \(!reserve_window\(active, NULL\)\) \{\s*const int error = errno;\s*milestone\("MEM_RESERVE_FAIL\(%llu\)'),
    "MEM_RESERVE_OK": (RUNTIME / "gamelib.c", r'milestone\("MEM_RESERVE_OK\(%llu\)[^;]*;\s*if \(aot_dispatch_bind_native'),
    "VK_DEVICE": (RUNTIME / "nvn/vulkan/device.c", r'milestone\("VK_DEVICE_%s\(%s, driver 0x%x\)'),
    "GAME_FIRST_FRAME": (RUNTIME / "nvn/objects.c", r'backend_present\(HOST\(NvnTexture, w->textures\[i\]\)\);\s*static bool first_frame;[^\n]*\n\s*if \(!__atomic_exchange_n\(&first_frame, true, __ATOMIC_RELAXED\)\) milestone\("GAME_FIRST_FRAME"\);'),
}

HARNESS = r'''#include "milestone.h"
int main(void) {
    milestone("MEM_RESERVE_OK(%llu) [0x%llx,0x%llx)", 13421772800ull, 0x7000000000ull, 0x7320000000ull);
    milestone("VK_DEVICE_%s(%s, driver 0x%x)%s%s", "FAIL", "Synthetic GPU", 0x80000000u, " ", "missing Vulkan features");
    milestone("GAME_FIRST_FRAME");
    return 0;
}
'''
EXPECTED = ["ACMilestone: MEM_RESERVE_OK(13421772800) [0x7000000000,0x7320000000)",
            "ACMilestone: VK_DEVICE_FAIL(Synthetic GPU, driver 0x80000000) missing Vulkan features",
            "ACMilestone: GAME_FIRST_FRAME"]


def main():
    for marker, (path, pattern) in SITES.items():
        if path == MAIN_ACTIVITY and not path.exists():
            print("APP_OPEN not checked: no shell/ next to this engine checkout")
            continue
        if not re.search(pattern, path.read_text()):
            raise RuntimeError(f"{marker} is no longer written where docs/DEVICE-MILESTONES.md says ({path.name})")
    device = (RUNTIME / "nvn/vulkan/device.c").read_text()
    if device.count("create_vk_device(&di);") != 2 or "VK_CHECK(vkCreateDevice" in device:
        raise RuntimeError("every vkCreateDevice must go through create_vk_device (VK_DEVICE_OK|FAIL)")
    if device.count('vk_device_milestone(false, "missing Vulkan features");') != 2:
        raise RuntimeError("both missing-feature fatal paths must log VK_DEVICE_FAIL")
    compiler = shutil.which("clang")
    if not compiler:
        raise RuntimeError("Host clang is required")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "harness.c").write_text(HARNESS)
    runner = OUT / "harness"
    subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-I", str(RUNTIME), str(OUT / "harness.c"),
                    "-o", str(runner)], check=True, timeout=45)
    lines = subprocess.run([str(runner)], check=True, capture_output=True, text=True, timeout=45).stderr.splitlines()
    if lines != EXPECTED:
        raise RuntimeError(f"unexpected milestone lines: {lines}")
    (OUT / "verification.json").write_text(json.dumps({"sites": sorted(SITES), "lines": lines}, indent=2) + "\n")
    print(f"device milestones: {len(SITES)} sites, {len(lines)} host lines OK (no device run)")


if __name__ == "__main__":
    main()
