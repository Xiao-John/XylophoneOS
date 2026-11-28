/* SPDX-License-Identifier: Apache-2.0
   XOS clock resolution without assuming a Linux kernel ABI.  */
#include <errno.h>
#include <time.h>
#include <shlib-compat.h>
#include "xos_cpu_time.h"
#include "xos_clock.h"
#include "xos_thread_extensions.h"

_Static_assert (sizeof (struct xos_cpu_time) == 72, "XOS CPU time ABI");

int
__clock_getres (clockid_t clock_id, struct timespec *res)
{
  unsigned long long resolution;
  if (clock_id <= -2 && clock_id != INT_MIN)
    {
      struct xos_thread_cpu_sample sample;
      int status = xos_thread_cpu_query (xos_thread_clock_decode (clock_id), &sample);
      if (status != 0) { __set_errno (status); return -1; }
      resolution = sample.resolution_ns;
    }
  else if (clock_id == CLOCK_PROCESS_CPUTIME_ID || clock_id == CLOCK_THREAD_CPUTIME_ID)
    {
      struct xos_cpu_time sample = { .version = 1, .size = sizeof (sample) };
      long int status = __xos_clock_trap (89, (unsigned long) &sample);
      if (status != 0)
        {
          __set_errno (status == -19 ? ENOTSUP : status == -5 ? ENOMEM : EIO);
          return -1;
        }
      resolution = sample.resolution_ns;
    }
  else if (clock_id == CLOCK_MONOTONIC || clock_id == CLOCK_REALTIME)
    {
      long int status = __xos_clock_trap (46, 1);
      if (status <= 0)
        {
          __set_errno (EIO);
          return -1;
        }
      resolution = (unsigned long) status;
    }
  else
    {
      __set_errno (EINVAL);
      return -1;
    }
  if (resolution == 0)
    {
      __set_errno (EIO);
      return -1;
    }
  if (res != 0)
    {
      res->tv_sec = resolution / 1000000000UL;
      res->tv_nsec = resolution % 1000000000UL;
    }
  return 0;
}
libc_hidden_def (__clock_getres)
versioned_symbol (libc, __clock_getres, clock_getres, GLIBC_2_17);
