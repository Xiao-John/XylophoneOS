/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include "xos_lll_futex.h"
#include "xos_timed_wait.h"
#include "xos_clock.h"

int
__xos_wait_monotonic (xos_u32 *word, xos_u32 expected, int has_deadline,
                       xos_i64 seconds, long nanoseconds)
{
  xos_u64 deadline = ~(xos_u64) 0;
  if (has_deadline)
    {
      if (nanoseconds < 0 || nanoseconds >= 1000000000L)
        return EINVAL;
      if (seconds < 0)
        return ETIMEDOUT;
      /* UINT64_MAX is XOS's infinite sentinel, not a finite deadline.  */
      xos_u64 max_finite = ~(xos_u64) 0 - 1;
      if ((xos_u64) seconds > (max_finite - (xos_u64) nanoseconds) / 1000000000ULL)
        return EOVERFLOW;
      deadline = (xos_u64) seconds * 1000000000ULL + (xos_u64) nanoseconds;
    }
  return -__xos_translate_wait (__xos_wait_word (word, expected, deadline));
}

int
__xos_wait_realtime (xos_u32 *word, xos_u32 expected, int has_deadline,
                    xos_i64 seconds, long nanoseconds)
{
  if (!has_deadline)
    return __xos_wait_monotonic (word, expected, 0, 0, 0);
  if (nanoseconds < 0 || nanoseconds >= 1000000000L)
    return EINVAL;
  if (seconds < 0)
    return ETIMEDOUT;
  const xos_u64 max_finite = ~(xos_u64) 0 - 1;
  if ((xos_u64) seconds > (max_finite - (xos_u64) nanoseconds) / 1000000000ULL)
    return EOVERFLOW;
  xos_u64 deadline = (xos_u64) seconds * 1000000000ULL + (xos_u64) nanoseconds;

  /* XOS realtime is a fixed boot-RTC offset from the monotonic clock.
     Sample monotonic first: preemption between the reads can only make
     the translated deadline earlier. Recheck realtime after an apparent
     timeout so this sampling skew cannot become an early public timeout.
     Neither the epoch nor errno participates in the native wait ABI. */
  for (;;)
    {
      long int monotonic = __xos_clock_trap (46, 0);
      long int realtime = __xos_clock_trap (64, 0);
      if (monotonic < 0)
        return EOVERFLOW;
      if (realtime < 0)
        return EIO;
      if (deadline <= (xos_u64) realtime)
        return ETIMEDOUT;
      xos_u64 remaining = deadline - (xos_u64) realtime;
      if (remaining > max_finite - (xos_u64) monotonic)
        return EOVERFLOW;
      int error = -__xos_translate_wait (
        __xos_wait_word (word, expected, (xos_u64) monotonic + remaining));
      if (error != ETIMEDOUT)
        return error;
    }
}
