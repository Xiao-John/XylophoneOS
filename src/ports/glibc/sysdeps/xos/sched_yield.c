/* SPDX-License-Identifier: Apache-2.0
   Yield the current XOS execution context.  */
#include <sched.h>

int
__sched_yield (void)
{
#ifdef XOS_GLIBC_YIELD_TEST
  extern void __xos_yield_test_trap (void);
  __xos_yield_test_trap ();
#else
# if !defined __x86_64__ || defined __ILP32__
#  error "XOS sched_yield supports x86-64 LP64 only"
# endif
  /* sys_yield schedules directly and does not define a return value in RAX.
     The call itself cannot fail; do not interpret the resumed register as an
     errno or Linux syscall result.  */
  unsigned long ignored;
  __asm__ volatile ("int $0x80" : "=a" (ignored)
                    : "a" (3UL), "D" (0UL), "S" (0UL), "d" (0UL)
                    : "memory", "cc");
#endif
  return 0;
}
libc_hidden_def (__sched_yield)
weak_alias (__sched_yield, sched_yield)
