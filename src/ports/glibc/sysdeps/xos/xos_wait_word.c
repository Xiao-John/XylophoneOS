/* SPDX-License-Identifier: Apache-2.0
   Internal bridge to XOS process-private wait and wake operations.  */
#include "xos_wait_word.h"

#if !defined XOS_GLIBC_WAIT_TEST && (!defined __x86_64__ || defined __ILP32__)
# error "XOS wait bridge supports x86-64 LP64 only"
#endif

/* Tests substitute the trap at compile time, never in production objects. */
#ifdef XOS_GLIBC_WAIT_TEST
extern xos_i64 __xos_wait_test_call (xos_u64, xos_u64, xos_u64);
# define xos_trap __xos_wait_test_call
#else
static inline xos_i64
xos_trap (xos_u64 number, xos_u64 first, xos_u64 second)
{
  xos_i64 result;
  __asm__ volatile ("int $0x80" : "=a" (result)
                    : "a" (number), "D" (first), "S" (second), "d" (0L)
                    : "memory", "cc");
  return result;
}
#endif

xos_i64
__xos_wait_word (xos_u32 *address, xos_u32 expected, xos_u64 deadline_ns)
{
  struct xos_wait_word_request request = {
    .version = 1, .size = sizeof (request), .header_reserved = 0,
    .address = (xos_u64) address, .deadline_ns = deadline_ns,
    .expected = expected, .reserved = 0
  };
  return xos_trap (48, (xos_u64) &request, 0);
}

xos_i64
__xos_wake_word (xos_u32 *address, xos_u32 count)
{
  return xos_trap (49, (xos_u64) address, count);
}
