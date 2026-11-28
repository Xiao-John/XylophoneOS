/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <time.h>

int __clock_nanosleep (clockid_t, int, const struct timespec *, struct timespec *);
static long monotonic, realtime, sleep_error;
static unsigned long deadlines[4];
static unsigned waits, reads, skew_first_wait;
long __xos_clock_test_trap (unsigned long number, unsigned long first)
{
  (void) first;
  if (number == 46) { ++reads; return monotonic; }
  if (number == 64) { ++reads; return realtime; }
  assert (0);
  return -1;
}
int __xos_sleep_until (unsigned long deadline, unsigned long *remaining)
{
  assert (waits < 4);
  deadlines[waits++] = deadline;
  if (sleep_error)
    {
      if (sleep_error == EINTR && remaining) *remaining = 17;
      return sleep_error;
    }
  long delta = (long) deadline - monotonic;
  monotonic = deadline;
  realtime += delta;
  if (skew_first_wait && waits == 1) realtime -= 4;
  return 0;
}
static void reset (void)
{
  monotonic = 100; realtime = 1000; sleep_error = 0;
  waits = reads = skew_first_wait = 0; errno = EDOM;
}
int main (void)
{
  struct timespec request = {0, 30}, remainder = {9, 8};
  reset ();
  assert (__clock_nanosleep (CLOCK_REALTIME, 0, &request, &remainder) == 0);
  assert (waits == 1 && deadlines[0] == 130 && reads == 1 && errno == EDOM);
  assert (remainder.tv_sec == 9 && remainder.tv_nsec == 8);
  reset (); request.tv_nsec = 140;
  assert (__clock_nanosleep (CLOCK_MONOTONIC, TIMER_ABSTIME, &request, NULL) == 0);
  assert (waits == 1 && deadlines[0] == 140);
  reset (); request.tv_nsec = 1030; skew_first_wait = 1;
  assert (__clock_nanosleep (CLOCK_REALTIME, TIMER_ABSTIME, &request, NULL) == 0);
  assert (waits == 2 && deadlines[0] == 130 && deadlines[1] == 134 && realtime == 1030);
  reset (); request.tv_nsec = 999;
  assert (__clock_nanosleep (CLOCK_REALTIME, TIMER_ABSTIME, &request, NULL) == 0 && waits == 0);
  request.tv_nsec = 99;
  assert (__clock_nanosleep (CLOCK_MONOTONIC, TIMER_ABSTIME, &request, NULL) == 0 && waits == 0);
  request.tv_nsec = 0;
  assert (__clock_nanosleep (CLOCK_MONOTONIC, 0, &request, NULL) == 0 && waits == 0);
  assert (__clock_nanosleep (CLOCK_MONOTONIC, 2, &request, NULL) == EINVAL);
  assert (__clock_nanosleep (987, 0, &request, NULL) == EINVAL);
  assert (__clock_nanosleep (CLOCK_PROCESS_CPUTIME_ID, 0, &request, NULL) == ENOTSUP);
  assert (__clock_nanosleep (CLOCK_THREAD_CPUTIME_ID, 0, &request, NULL) == ENOTSUP);
  assert (__clock_nanosleep (CLOCK_MONOTONIC, 0, NULL, NULL) == EFAULT);
  request.tv_sec = -1;
  assert (__clock_nanosleep (CLOCK_MONOTONIC, 0, &request, NULL) == EINVAL);
  request = (struct timespec) {0, 1000000000L};
  assert (__clock_nanosleep (CLOCK_MONOTONIC, 0, &request, NULL) == EINVAL);
  request.tv_nsec = -1;
  assert (__clock_nanosleep (CLOCK_MONOTONIC, 0, &request, NULL) == EINVAL);
  request = (struct timespec) {LONG_MAX, 0};
  assert (__clock_nanosleep (CLOCK_MONOTONIC, 0, &request, NULL) == EOVERFLOW);
  request = (struct timespec) {0, 30}; monotonic = LONG_MAX - 20;
  assert (__clock_nanosleep (CLOCK_MONOTONIC, 0, &request, NULL) == EOVERFLOW);
  reset (); monotonic = LONG_MAX - 20; request.tv_nsec = 1030;
  assert (__clock_nanosleep (CLOCK_REALTIME, TIMER_ABSTIME, &request, NULL) == EOVERFLOW);
  assert (waits == 0 && errno == EDOM);
  monotonic = -1; request.tv_nsec = 30;
  assert (__clock_nanosleep (CLOCK_MONOTONIC, 0, &request, NULL) == EOVERFLOW);
  reset (); realtime = -5;
  assert (__clock_nanosleep (CLOCK_REALTIME, TIMER_ABSTIME, &request, NULL) == EIO);
  reset (); sleep_error = ENOTSUP;
  assert (__clock_nanosleep (CLOCK_MONOTONIC, 0, &request, &remainder) == ENOTSUP);
  reset (); sleep_error = EIO;
  assert (__clock_nanosleep (CLOCK_MONOTONIC, 0, &request, &remainder) == EIO);
  reset (); sleep_error = EIO;
  assert (__clock_nanosleep (CLOCK_MONOTONIC, 0, &request, &remainder) == EIO);
  assert (errno == EDOM && remainder.tv_sec == 9 && remainder.tv_nsec == 8);
  reset (); sleep_error = EINTR;
  assert (__clock_nanosleep (CLOCK_MONOTONIC, 0, &request, &remainder) == EINTR);
  assert (remainder.tv_sec == 0 && remainder.tv_nsec == 17 && errno == EDOM);
  remainder = (struct timespec) {9, 8}; request.tv_nsec = 140;
  assert (__clock_nanosleep (CLOCK_MONOTONIC, TIMER_ABSTIME, &request, &remainder) == EINTR);
  assert (remainder.tv_sec == 9 && remainder.tv_nsec == 8 && errno == EDOM);
  puts ("CLOCK_SLEEP_HOST_PASS cases=24 deadlines skew overflow failures errno remainder interruption");
}
