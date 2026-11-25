/* SPDX-License-Identifier: Apache-2.0
   XOS does not yet implement pthread cancellation.  */
#include <errno.h>
#include <pthread.h>
#include <shlib-compat.h>

int
__pthread_cancel (pthread_t thread)
{
  (void) thread;
  /* pthread interfaces return the error number rather than setting errno.  */
  return ENOTSUP;
}
versioned_symbol (libc, __pthread_cancel, pthread_cancel, GLIBC_2_34);
