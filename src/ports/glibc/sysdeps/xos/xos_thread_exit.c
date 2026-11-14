/* SPDX-License-Identifier: Apache-2.0
   Terminate a non-final XOS thread using the native exit handshake.  */
#include "xos_thread_exit.h"
#if !defined XOS_GLIBC_THREAD_TEST && (!defined __x86_64__ || defined __ILP32__)
# error "XOS thread exit supports x86-64 LP64 only"
#endif
#ifdef XOS_GLIBC_THREAD_TEST
extern long __xos_thread_test_trap (unsigned long, unsigned long);
# define xos_thread_trap __xos_thread_test_trap
#else
static inline long
xos_thread_trap (unsigned long number, unsigned long first)
{
  long result;
  __asm__ volatile ("int $0x80" : "=a" (result)
                    : "a" (number), "D" (first), "S" (0UL), "d" (0UL)
                    : "memory", "cc");
  return result;
}
#endif

void
__xos_internal_exit (int status)
{
  /* The kernel requires begin_exit before thread_exit.  A last-thread result
     here contradicts NPTL's caller, which already observed another thread;
     fail the process closed rather than skip glibc's last-thread cleanup.  */
  if (xos_thread_trap (42, 0) == 0)
    (void) xos_thread_trap (43, (unsigned long) (long) status);
  (void) xos_thread_trap (2, 127);
  __builtin_trap ();
}
