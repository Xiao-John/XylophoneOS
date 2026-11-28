/* SPDX-License-Identifier: Apache-2.0
   XOS elapsed-time waits use the existing monotonic wait-word mechanism.
   The upstream nanosleep wrapper translates this function's error number. */
#include <errno.h>
#include <limits.h>
#include <time.h>
#include <shlib-compat.h>
#include "xos_clock.h"
#include "xos_sleep.h"

int
__clock_nanosleep (clockid_t clock_id, int flags, const struct timespec *request,
                   struct timespec *remaining)
{
  /* Interruption is explicit and scoped to a captured active-wait ticket.
     Signals and pthread cancellation remain unsupported. */
  if (request == NULL)
    return EFAULT;
  if (flags != 0 && flags != TIMER_ABSTIME)
    return EINVAL;
  if (request->tv_sec < 0 || request->tv_nsec < 0
      || request->tv_nsec >= 1000000000L)
    return EINVAL;
  if (clock_id == CLOCK_PROCESS_CPUTIME_ID || clock_id == CLOCK_THREAD_CPUTIME_ID)
    return ENOTSUP;
  if (clock_id != CLOCK_MONOTONIC && clock_id != CLOCK_REALTIME)
    return EINVAL;
  /* XOS clock reads are signed non-negative nanoseconds. Keep deadlines
     in that same representable domain and exclude the infinite sentinel. */
  const unsigned long maximum = LONG_MAX;
  if ((unsigned long) request->tv_sec
      > (maximum - (unsigned long) request->tv_nsec) / 1000000000UL)
    return EOVERFLOW;
  unsigned long value = (unsigned long) request->tv_sec * 1000000000UL
    + (unsigned long) request->tv_nsec;
  if (value == 0)
    return 0;

  if (flags == TIMER_ABSTIME && clock_id == CLOCK_REALTIME)
    {
      /* Read monotonic first, then recheck realtime after waking. A
         preemption between samples may shorten the first native wait,
         but cannot make the public operation finish before its deadline.
         Realtime currently has a fixed boot-RTC offset; no setter exists. */
      for (;;)
        {
          long monotonic = __xos_clock_trap (46, 0);
          long realtime = __xos_clock_trap (64, 0);
          if (monotonic < 0)
            return EOVERFLOW;
          if (realtime < 0)
            return EIO;
          if (value <= (unsigned long) realtime)
            return 0;
          unsigned long delta = value - (unsigned long) realtime;
          if (delta > maximum - (unsigned long) monotonic)
            return EOVERFLOW;
          int error = __xos_sleep_until ((unsigned long) monotonic + delta, NULL);
          if (error != 0)
            return error;
        }
    }

  long monotonic = __xos_clock_trap (46, 0);
  if (monotonic < 0)
    return EOVERFLOW;
  if (flags == 0)
    {
      /* Relative REALTIME waits measure elapsed time, independent of the
         wall-clock epoch, just like upstream nanosleep requires. */
      if (value > maximum - (unsigned long) monotonic)
        return EOVERFLOW;
      value += (unsigned long) monotonic;
    }
  if (value <= (unsigned long) monotonic)
    return 0;
  xos_u64 remainder;
  int error = __xos_sleep_until (value, &remainder);
  if (error == EINTR && flags == 0 && remaining != NULL)
    *remaining = (struct timespec) {
      remainder / 1000000000UL, remainder % 1000000000UL
    };
  return error;
}
libc_hidden_def (__clock_nanosleep)
versioned_symbol (libc, __clock_nanosleep, clock_nanosleep, GLIBC_2_17);
