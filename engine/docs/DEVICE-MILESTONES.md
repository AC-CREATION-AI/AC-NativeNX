# Device-run milestones

A device test report must tell apart four states that the logs used to blur: the app opened, the guest memory
was reserved, a Vulkan device was created, the game drew its first frame. Each one writes a single logcat line
with the tag `ACMilestone`:

```sh
adb logcat -c                # before launching
adb logcat -s ACMilestone    # while the app runs
```

| Marker | Written by | Meaning |
|---|---|---|
| `APP_OPEN <package>` | `shell/.../ui/main/MainActivity.kt` `onCreate` | the launcher activity is up. `(recreated)` is appended when Android recreates it (rotation, fold) |
| `MEM_RESERVE_OK(<bytes>) [lo,hi)` | `engine/ports/shared-android/runtime/gamelib.c` | the fixed guest window is reserved; `<bytes>` is its size |
| `MEM_RESERVE_FAIL(<bytes>) [lo,hi) errno <n>` | same | the reservation failed (errno 17 = EEXIST: another mapping holds the window, see ACC-3216); the session stops there |
| `VK_DEVICE_OK(<GPU>, driver 0x<version>)` | `engine/ports/shared-android/runtime/nvn/vulkan/device.c` | `vkCreateDevice` succeeded on that GPU and driver |
| `VK_DEVICE_FAIL(<GPU>, driver 0x<version>) <why>` | same | the driver lacks a required feature or `vkCreateDevice` failed; the existing fatal message follows |
| `GAME_FIRST_FRAME` | `engine/ports/shared-android/runtime/nvn/objects.c` `nvnQueuePresentTexture` | the game itself presented its first frame (the shader-preparation screen before it does not count) |

Reading a report: the last marker reached is the state. `APP_OPEN` alone means the game process never got to its
memory reservation; `MEM_RESERVE_OK` without a `VK_DEVICE_*` line means it stopped before the GPU (or before Vulkan
was initialised: "no Vulkan driver" and "no Vulkan 1.3 device" are logged by the fatal path, not as a marker);
`VK_DEVICE_OK` without `GAME_FIRST_FRAME` means the game did not present. A missing line is "not reached", never
"passed".

The markers are logged once per process (`APP_OPEN` once per activity creation). They carry no path, key, title
or user data. `python3 tools/check_device_milestones.py` checks on the host that each marker is still written
where this table says and that the native helper prints the expected line; it does not run anything on a device.
