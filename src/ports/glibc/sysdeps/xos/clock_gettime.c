/* SPDX-License-Identifier: Apache-2.0
   XOS wall, monotonic and current process/thread CPU clocks.  */
#include <errno.h>
#include <time.h>
#include <shlib-compat.h>
#include "xos_cpu_time.h"
#include "xos_clock.h"

_Static_assert (sizeof (struct xos_cpu_time) == 72, "XOS CPU time ABI");

int
__clock_gettime (clockid_t clock_id, struct timespec *tp)
{
  unsigned long long total;
  if (clock_id == CLOCK_PROCESS_CPUTIME_ID || clock_id == CLOCK_THREAD_CPUTIME_ID)
    {
      struct xos_cpu_time sample = { .version = 1, .size = sizeof (sample) };
      long int result = __xos_clock_trap (89, (unsigned long) &sample);
      if (result != 0)
        {
          __set_errno (result == -19 ? ENOTSUP : result == -5 ? ENOMEM : EIO);
          return -1;
        }
      unsigned long long user = clock_id == CLOCK_PROCESS_CPUTIME_ID
        ? sample.user_ns : sample.thread_user_ns;
      unsigned long long system = clock_id == CLOCK_PROCESS_CPUTIME_ID
        ? sample.system_ns : sample.thread_system_ns;
      if (system > (unsigned long long) -1 - user)
        {
          __set_errno (EOVERFLOW);
          return -1;
        }
      total = user + system;
    }
  else
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
      long int value = __xos_clock_trap (number, 0);
      if (value < 0)
        {
          /* The monotonic ABI returns unsigned nanoseconds via signed RAX;
             values beyond INT64_MAX are not representable by this interface.
             Realtime currently returns -5 on an invalid RTC.  */
          __set_errno (number == 46 ? EOVERFLOW : EIO);
          return -1;
        }
      total = (unsigned long) value;
    }
  tp->tv_sec = total / 1000000000UL;
  tp->tv_nsec = total % 1000000000UL;
  return 0;
}
libc_hidden_def (__clock_gettime)
versioned_symbol (libc, __clock_gettime, clock_gettime, GLIBC_2_17);
