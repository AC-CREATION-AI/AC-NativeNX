---
name: perf-report
description: Use when measuring or comparing AC-NativeNX performance (FPS, frame pacing, load time, thermals) on a real device and filing a comparable report. No build tools required.
---

# Performance report

A report is only useful if two people can compare it. Fixed scene, fixed protocol, real device.

## Protocol

1. Same build, stated by version or full commit SHA. Same settings, all listed (resolution scale,
   GPU driver, CPU backend, any enabled option). Battery above 50%, not charging, airplane mode off
   or on (say which), screen brightness fixed, device cool (wait 5 minutes after a previous run).
2. Pick a scene that can be reproduced: a named location or menu, same save state if the user has one.
   Describe it in one sentence so others can reach it.
3. Run 3 minutes. Record: average FPS, 1% low FPS, and whether the game ran at correct speed
   (displayed FPS is not game speed: note too fast, too slow, audio drift).
4. Optional: thermal state at end, time to first frame after launch.
5. Repeat once. Report both runs. If they differ by more than 10%, say so.

## Rules

- Never claim a performance win from a change that lowers quality or adds waiting; show before/after on
  the same protocol and settings.
- No game files or keys in logs or screenshots.
- If you did not measure on a device, say "not device-measured". Estimates are not measurements.

## Submit

Open an issue with the **Performance report** form (`.github/ISSUE_TEMPLATE/perf_report.yml`). Add
`Agent: <name> · Model: <id>` when an agent filled it in, and who took the measurement.
