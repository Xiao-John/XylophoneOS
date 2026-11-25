/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <pthreadP.h>
#include <shlib-compat.h>

int
__pthread_getaffinity_np (pthread_t thread, size_t size, cpu_set_t *mask)
{
  /* CPU affinity is not part of the XOS thread ABI. */
  (void) thread;
  (void) size;
  (void) mask;
  return ENOTSUP;
}
libc_hidden_def (__pthread_getaffinity_np)
versioned_symbol (libc, __pthread_getaffinity_np, pthread_getaffinity_np,
                  GLIBC_2_32);
