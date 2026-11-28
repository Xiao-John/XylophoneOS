/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <pthreadP.h>
#include <shlib-compat.h>
#include "xos_thread_extensions.h"

int
__pthread_getcpuclockid (pthread_t thread, clockid_t *clockid)
{
  if (clockid == NULL) return EINVAL;
  int encoded;
  int status = xos_thread_clock_encode ((unsigned long) thread, &encoded);
  if (status != 0) return status;
  struct xos_thread_cpu_sample sample;
  status = xos_thread_cpu_query ((unsigned long) thread, &sample);
  if (status != 0) return status;
  *clockid = encoded;
  return 0;
}
versioned_symbol (libc, __pthread_getcpuclockid, pthread_getcpuclockid,
                  GLIBC_2_34);
