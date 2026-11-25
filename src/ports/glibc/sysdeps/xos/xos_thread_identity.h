/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_GLIBC_THREAD_IDENTITY_H
#define XOS_GLIBC_THREAD_IDENTITY_H 1

#include <errno.h>
#include "xos_thread_create.h"

struct xos_thread_info
{
  struct xos_thread_header header;
  xos_u64 pid, tid, stack_bottom, stack_top, thread_pointer;
};

_Static_assert (sizeof (struct xos_thread_info) == 56, "XOS thread info ABI");
_Static_assert (sizeof (pthread_t) == sizeof (xos_u64), "XOS pthread handle ABI");

static inline xos_i64
xos_thread_lifecycle (xos_u64 number, xos_u64 first, xos_u64 second)
{
#ifdef XOS_GLIBC_IDENTITY_TEST
  extern xos_i64 __xos_thread_identity_test_call (xos_u64, xos_u64, xos_u64);
  return __xos_thread_identity_test_call (number, first, second);
#else
  xos_i64 result;
  __asm__ volatile ("int $0x80" : "=a" (result)
                    : "a" (number), "D" (first), "S" (second), "d" (0UL)
                    : "memory", "cc");
  return result;
#endif
}

static inline int
xos_thread_lifecycle_error (xos_i64 result)
{
  switch (result)
    {
    case -2: return EINVAL;
    case -6: return EBUSY;
    case -11: return EFAULT;
    case -12: return EBUSY;
    case -15: return ESRCH;
    case -16: return EDEADLK;
    default: return EIO;
    }
}

#endif
