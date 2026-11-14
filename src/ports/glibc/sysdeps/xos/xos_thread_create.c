/* SPDX-License-Identifier: Apache-2.0 */
#include "xos_thread_create.h"

#if !defined XOS_GLIBC_THREAD_TEST && (!defined __x86_64__ || defined __ILP32__)
# error "XOS thread bridge supports x86-64 LP64 only"
#endif
_Static_assert (sizeof (struct xos_thread_prepare_request) == 40, "prepare ABI");
_Static_assert (sizeof (struct xos_thread_reservation) == 56, "reservation ABI");
_Static_assert (sizeof (struct xos_thread_start_request) == 56, "start ABI");

#ifdef XOS_GLIBC_THREAD_TEST
extern xos_i64 __xos_thread_test_call (xos_u64, xos_u64, xos_u64);
# define xos_trap __xos_thread_test_call
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
__xos_thread_prepare (xos_u64 stack, xos_u64 tls, xos_u64 flags,
                      struct xos_thread_reservation *reservation)
{
  struct xos_thread_prepare_request request = {
    .header = { 1, sizeof (request), 0 },
    .stack_bytes = stack, .tls_bytes = tls, .flags = flags
  };
  return xos_trap (38, (xos_u64) &request, (xos_u64) reservation);
}

xos_i64
__xos_thread_start (xos_u64 tid, xos_u64 entry, xos_u64 argument,
                    xos_u64 stack, xos_u64 thread_pointer)
{
  struct xos_thread_start_request request = {
    .header = { 1, sizeof (request), 0 },
    .tid = tid, .entry = entry, .argument = argument, .stack = stack,
    .thread_pointer = thread_pointer
  };
  return xos_trap (39, (xos_u64) &request, 0);
}

xos_i64
__xos_thread_abort (xos_u64 tid)
{
  return xos_trap (40, tid, 0);
}
