/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include "xos_lll_futex.h"
#include "xos_timed_wait.h"

int
__xos_wait_monotonic (xos_u32 *word, xos_u32 expected, int has_deadline,
                       xos_i64 seconds, long nanoseconds)
{
  xos_u64 deadline = ~(xos_u64) 0;
  if (has_deadline)
    {
      if (seconds < 0)
        return ETIMEDOUT;
      if (nanoseconds < 0 || nanoseconds >= 1000000000L)
        return EINVAL;
      /* UINT64_MAX is XOS's infinite sentinel, not a finite deadline.  */
      xos_u64 max_finite = ~(xos_u64) 0 - 1;
      if ((xos_u64) seconds > (max_finite - (xos_u64) nanoseconds) / 1000000000ULL)
        return EOVERFLOW;
      deadline = (xos_u64) seconds * 1000000000ULL + (xos_u64) nanoseconds;
    }
  return -__xos_translate_wait (__xos_wait_word (word, expected, deadline));
}
