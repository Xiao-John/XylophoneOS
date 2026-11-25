/* SPDX-License-Identifier: Apache-2.0
   Terminate an XOS thread using the native exit handshake.  */
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
__xos_thread_finish (unsigned long result, void (*last_process_exit) (void))
{
  long election = xos_thread_trap (42, 0);
  if (election == 0)
    (void) xos_thread_trap (43, result);
  else if (election == 1 && last_process_exit != 0)
    last_process_exit ();
  (void) xos_thread_trap (2, 127);
  __builtin_trap ();
}

void
__xos_internal_exit (int status)
{
  __xos_thread_finish ((unsigned long) (long) status, 0);
}
