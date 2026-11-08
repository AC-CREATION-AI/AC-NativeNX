/* Device-run milestones, so a test report tells apart "app opened", "guest memory reserved", "Vulkan device created"
 * and "game drew its first frame" (docs/DEVICE-MILESTONES.md). One line per milestone, logcat tag ACMilestone:
 *     adb logcat -s ACMilestone
 * The Java side (shell MainActivity) writes APP_OPEN with the same tag. */
#pragma once
#include <stdarg.h>
#include <stdio.h>
#ifdef __ANDROID__
#include <android/log.h>
#endif

#define MILESTONE_TAG "ACMilestone"

static inline void __attribute__((format(printf, 1, 2))) milestone(const char *fmt, ...) {
    char line[256];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(line, sizeof line, fmt, ap);
    va_end(ap);
#ifdef __ANDROID__
    // Straight to logcat: stderr reaches it only through the runtime's pipe thread, which may not run yet.
    __android_log_write(ANDROID_LOG_INFO, MILESTONE_TAG, line);
#else
    fprintf(stderr, MILESTONE_TAG ": %s\n", line);
#endif
}
