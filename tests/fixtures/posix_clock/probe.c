/* SPDX-License-Identifier: Apache-2.0 */
/* P0 clock functions: clock_gettime / clock_getres / clock_settime /
   clock_nanosleep / nanosleep. */
#include <errno.h>
#include <stdio.h>
#include <time.h>

/* x86_64-elf newlib does not set _POSIX_TIMERS / _POSIX_MONOTONIC_CLOCK
   (gated behind __rtems__/__CYGWIN__), so declare what we use. */
#ifndef CLOCK_REALTIME
#define CLOCK_REALTIME 1
#endif
#ifndef CLOCK_MONOTONIC
#define CLOCK_MONOTONIC 4
#endif
#ifndef CLOCK_MONOTONIC_RAW
#define CLOCK_MONOTONIC_RAW 5
#endif
#ifndef TIMER_ABSTIME
#define TIMER_ABSTIME 4
#endif
int clock_gettime(clockid_t, struct timespec*);
int clock_getres(clockid_t, struct timespec*);
int clock_settime(clockid_t, const struct timespec*);
int clock_nanosleep(clockid_t, int, const struct timespec*, struct timespec*);
int nanosleep(const struct timespec*, struct timespec*);

#ifndef CLOCK_REALTIME
#define CLOCK_REALTIME 1
#endif
#ifndef CLOCK_MONOTONIC
#define CLOCK_MONOTONIC 4
#endif
#ifndef CLOCK_MONOTONIC_RAW
#define CLOCK_MONOTONIC_RAW 5
#endif
#ifndef TIMER_ABSTIME
#define TIMER_ABSTIME 4
#endif

static int failures;

static void check(const char* name, int ok) {
    printf("%s=%d\n", name, ok ? 1 : 0);
    if (!ok) { ++failures; }
}

int main(void) {
    struct timespec ts, ts2, res;

    // clock_gettime: CLOCK_REALTIME
    check("clock_gettime_realtime", clock_gettime(CLOCK_REALTIME, &ts) == 0
           && ts.tv_sec > 1700000000);

    // clock_gettime: CLOCK_MONOTONIC
    check("clock_gettime_monotonic", clock_gettime(CLOCK_MONOTONIC, &ts) == 0
           && ts.tv_sec >= 0);

    // clock_gettime: CLOCK_MONOTONIC_RAW
    check("clock_gettime_monotonic_raw", clock_gettime(CLOCK_MONOTONIC_RAW, &ts) == 0
           && ts.tv_sec >= 0);

    // clock_gettime: monotonic is non-decreasing
    clock_gettime(CLOCK_MONOTONIC, &ts);
    clock_gettime(CLOCK_MONOTONIC, &ts2);
    check("monotonic_non_decreasing",
          ts2.tv_sec > ts.tv_sec ||
          (ts2.tv_sec == ts.tv_sec && ts2.tv_nsec >= ts.tv_nsec));

    // clock_gettime: null pointer
    errno = 0;
    check("clock_gettime_null", clock_gettime(CLOCK_MONOTONIC, NULL) == -1
           && errno == EFAULT);

    // clock_gettime: unsupported clock
    errno = 0;
    check("clock_gettime_bad", clock_gettime(999, &ts) == -1 && errno == EINVAL);

    // clock_getres: CLOCK_REALTIME
    check("clock_getres_realtime", clock_getres(CLOCK_REALTIME, &res) == 0
           && res.tv_sec == 0 && res.tv_nsec > 0);

    // clock_getres: CLOCK_MONOTONIC
    check("clock_getres_monotonic", clock_getres(CLOCK_MONOTONIC, &res) == 0
           && res.tv_sec == 0 && res.tv_nsec > 0);

    // clock_getres: unsupported clock
    errno = 0;
    check("clock_getres_bad", clock_getres(999, &res) == -1 && errno == EINVAL);

    // clock_settime: EPERM
    errno = 0;
    check("clock_settime_eperm", clock_settime(CLOCK_REALTIME, &ts) == -1
           && errno == EPERM);

    // clock_nanosleep: relative, short sleep
    struct timespec sleep_req = {0, 50'000'000};  // 50 ms
    struct timespec before, after;
    clock_gettime(CLOCK_MONOTONIC, &before);
    check("clock_nanosleep_rel", clock_nanosleep(CLOCK_MONOTONIC, 0, &sleep_req, NULL) == 0);
    clock_gettime(CLOCK_MONOTONIC, &after);
    check("clock_nanosleep_duration",
          after.tv_sec * 1000000000LL + after.tv_nsec -
          (before.tv_sec * 1000000000LL + before.tv_nsec) >= 40000000LL);

    // clock_nanosleep: absolute, already passed
    struct timespec past = {0, 0};
    check("clock_nanosleep_abs_past",
          clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &past, NULL) == 0);

    // clock_nanosleep: invalid nsec
    struct timespec bad_req = {0, 1000000000L};
    errno = 0;
    check("clock_nanosleep_bad_nsec", clock_nanosleep(CLOCK_MONOTONIC, 0, &bad_req, NULL) == -1
           && errno == EINVAL);

    // nanosleep: relative
    struct timespec nano_req = {0, 30'000'000};  // 30 ms
    check("nanosleep", nanosleep(&nano_req, NULL) == 0);

    printf("failures=%d\n", failures);
    puts(failures == 0 ? "CLOCK_OK" : "CLOCK_FAILED");
    return failures == 0 ? 0 : 1;
}
