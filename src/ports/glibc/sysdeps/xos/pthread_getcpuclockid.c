/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <pthreadP.h>
#include <shlib-compat.h>

int
__pthread_getcpuclockid (pthread_t thread, clockid_t *clockid)
{
  /* Native CPU accounting only reads the calling thread. */
  (void) thread;
  (void) clockid;
  return ENOTSUP;
}
versioned_symbol (libc, __pthread_getcpuclockid, pthread_getcpuclockid,
                  GLIBC_2_34);
