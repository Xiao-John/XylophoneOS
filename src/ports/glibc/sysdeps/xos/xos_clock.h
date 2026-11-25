/* SPDX-License-Identifier: Apache-2.0
   Private raw XOS clock trap; callers translate each operation's errors.  */
#ifndef XOS_GLIBC_CLOCK_H
#define XOS_GLIBC_CLOCK_H 1
static inline long int
__xos_clock_trap (unsigned long number, unsigned long first)
{
#ifdef XOS_GLIBC_CLOCK_TEST
  extern long int __xos_clock_test_trap (unsigned long, unsigned long);
  return __xos_clock_test_trap (number, first);
#else
# if !defined __x86_64__ || defined __ILP32__
#  error "XOS clock support requires x86-64 LP64"
# endif
  long int value;
  __asm__ volatile ("int $0x80" : "=a" (value)
                    : "a" (number), "D" (first), "S" (0UL), "d" (0UL)
                    : "memory", "cc");
  return value;
#endif
}
#endif
