/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <pthread.h>
#include <shlib-compat.h>

int
__pthread_getattr_np (pthread_t thread, pthread_attr_t *attribute)
{
  /* Native TIDs are opaque. The generic implementation reads a TCB pointer.
     Attribute snapshots need a separate XOS thread registry contract. */
  (void) thread;
  (void) attribute;
  return ENOTSUP;
}
versioned_symbol (libc, __pthread_getattr_np, pthread_getattr_np, GLIBC_2_32);
