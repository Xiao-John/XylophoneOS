/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <pthreadP.h>
#include <shlib-compat.h>

int
__pthread_setaffinity_new (pthread_t thread, size_t size, const cpu_set_t *mask)
{
  /* CPU affinity is not part of the XOS thread ABI. */
  (void) thread;
  (void) size;
  (void) mask;
  return ENOTSUP;
}
versioned_symbol (libc, __pthread_setaffinity_new, pthread_setaffinity_np,
                  GLIBC_2_34);
