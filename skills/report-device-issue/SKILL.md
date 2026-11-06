---
name: report-device-issue
description: Use when a user sees a crash, black screen, wrong audio/video or startup failure of AC-NativeNX on an Android device and wants a reproducible bug report. No build tools required. Collects device, GPU, driver, build and logs without any game content.
---

# Report a device issue

You do not need to build anything. Produce an issue that someone else can reproduce.

## Never include

Game files, keys (`prod.keys`, `title.keys`), firmware, saves, dumped shaders, or paths revealing
where the user keeps them. Strip game titles' text from logs if it contains game data. Game
*name and version number* are fine; hashes of the user's dump are not.

## Collect (ask the user, or read from adb if connected)

1. App version: Settings/About, or the APK file name `AC-NativeNX-<version>-...`; if built from source,
   the full commit SHA.
2. Device model, Android version, SoC and GPU (e.g. Galaxy Z Fold, Snapdragon 8 Gen 2, Adreno 740).
   Mali/other GPUs are unsupported: the app should say so instead of crashing; report a crash anyway.
3. GPU driver: stock vendor version, or the custom driver package and version.
4. Game name and **version number**, and whether keys/firmware were configured in the app.
5. Exact steps from a fresh launch, what you expected, what happened, how often.
6. Logs: `adb logcat -d -b crash` and the last 300 lines of `adb logcat -d | grep -i -E "nativenx|vulkan|fatal"`.
   Check for key material or game text before pasting.
7. Did it work in an earlier build? Which one?

## Submit

Open an issue with the **Bug report** form (`.github/ISSUE_TEMPLATE/bug_report.yml`) and fill every
required field. Add the line `Agent: <name> · Model: <id>` if an agent wrote it. Say plainly whether the
agent ran anything itself or the human provided every observation.
