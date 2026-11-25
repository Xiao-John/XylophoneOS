/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <pthreadP.h>
#include <shlib-compat.h>

int
__pthread_setschedprio (pthread_t thread, int priority)
{
  /* XOS does not expose per-thread priority changes. */
  (void) thread;
  (void) priority;
  return ENOTSUP;
}
versioned_symbol (libc, __pthread_setschedprio, pthread_setschedprio,
                  GLIBC_2_34);
