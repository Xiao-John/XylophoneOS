/* SPDX-License-Identifier: Apache-2.0
   XOS wall and monotonic clocks, expressed as nanoseconds.  */
#include <errno.h>
#include <time.h>
#include <shlib-compat.h>

int
__clock_gettime (clockid_t clock_id, struct timespec *tp)
{
  unsigned long number;
  if (clock_id == CLOCK_MONOTONIC)
    number = 46;
  else if (clock_id == CLOCK_REALTIME)
    number = 64;
  else
    {
      __set_errno (EINVAL);
      return -1;
    }
  long int value;
#ifdef XOS_GLIBC_CLOCK_TEST
  extern long int __xos_clock_test_trap (unsigned long);
  value = __xos_clock_test_trap (number);
#else
# if !defined __x86_64__ || defined __ILP32__
#  error "XOS clock_gettime supports x86-64 LP64 only"
# endif
  __asm__ volatile ("int $0x80" : "=a" (value)
                    : "a" (number), "D" (0UL), "S" (0UL), "d" (0UL)
                    : "memory", "cc");
#endif
  if (value < 0)
    {
      /* The monotonic ABI returns unsigned nanoseconds via signed RAX;
         values beyond INT64_MAX are not representable by this interface.
         Realtime currently returns -5 on an invalid RTC.  */
      __set_errno (number == 46 ? EOVERFLOW : EIO);
      return -1;
    }
  tp->tv_sec = value / 1000000000L;
  tp->tv_nsec = value % 1000000000L;
  return 0;
}
libc_hidden_def (__clock_gettime)
versioned_symbol (libc, __clock_gettime, clock_gettime, GLIBC_2_17);
