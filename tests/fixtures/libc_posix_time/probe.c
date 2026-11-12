/* SPDX-License-Identifier: Apache-2.0 */
/* Link and behaviour probe for the POSIX time and file-metadata surface. */
#include <unistd.h>
#include <time.h>
#include <errno.h>
#include <stdio.h>
#include <sys/stat.h>
#include <sys/times.h>
#include <utime.h>

int main(void) {
    const clock_t clock_first = clock();
    struct tms usage;
    const clock_t ticks = times(&usage);
    const clock_t clock_second = clock();

    struct timespec stamp = {0, 0};
    const int base = timespec_get(&stamp, TIME_UTC);
    struct utimbuf times_value = {0, 0};
    errno = 0;
    const int utime_result = utime("/case/file", &times_value);
    const int utime_errno = errno;
    errno = 0;
    const int chmod_result = chmod("/case/file", 0644);
    const int chmod_errno = errno;
    errno = 0;
    const int chown_result = chown("/case/file", 0, 0);
    const int chown_errno = errno;

    printf("clock_first=%ld clock_second=%ld ticks=%ld\n",
           (long)clock_first, (long)clock_second, (long)ticks);
    printf("timespec_get=%d sec=%ld nsec=%ld\n", base, (long)stamp.tv_sec, (long)stamp.tv_nsec);
    printf("utime=%d/%d chmod=%d/%d chown=%d/%d\n",
           utime_result, utime_errno, chmod_result, chmod_errno, chown_result, chown_errno);

    const int ok = clock_first >= 0 && clock_second >= clock_first
        && ticks != (clock_t)-1 && usage.tms_utime >= 0
        && base == TIME_UTC && stamp.tv_sec > 0 && stamp.tv_nsec >= 0 && stamp.tv_nsec < 1000000000L
        && utime_result == -1 && utime_errno == ENOSYS
        && chmod_result == -1 && chmod_errno == ENOSYS
        && chown_result == -1 && chown_errno == ENOSYS;
    puts(ok ? "LIBC_TIME_OK" : "LIBC_TIME_FAILED");
    return ok ? 0 : 1;
}
