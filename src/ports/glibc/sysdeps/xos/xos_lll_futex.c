/* SPDX-License-Identifier: Apache-2.0
   Translate XOS private wait-word results to glibc low-level return values. */
#include <errno.h>
#include "xos_lll_futex.h"
#include "xos_wait_word.h"

static int
translate_wait (xos_i64 result)
{
  switch (result)
    {
    case 0: return 0;
    case -14: return -EAGAIN; /* thread_value_changed */
    case -13: return -ETIMEDOUT;
    case -11: return -EFAULT;
    case -12: return -EBUSY;
    case -2: return -EINVAL;
    case -5: return -ENOMEM;
    default: return -EIO;
    }
}

int
__xos_lll_wait (unsigned int *word, unsigned int expected)
{
  return translate_wait (__xos_wait_word (word, expected, ~(xos_u64) 0));
}

int
__xos_lll_wake (unsigned int *word, int count)
{
  if (count < 0)
    return -EINVAL;
  xos_i64 result = __xos_wake_word (word, (xos_u32) count);
  /* glibc low-level callers want zero for any nonnegative wake count.  */
  return result >= 0 ? 0 : translate_wait (result);
}
