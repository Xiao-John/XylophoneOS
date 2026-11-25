/* SPDX-License-Identifier: Apache-2.0 */
#include <pthreadP.h>
#include <signal.h>
#include <shlib-compat.h>

int
__pthread_sigqueue (pthread_t thread, int signal, const union sigval value)
{
  /* With no queued delivery, only a signal-zero query can succeed. */
  (void) value;
  return __pthread_kill (thread, signal);
}
versioned_symbol (libc, __pthread_sigqueue, pthread_sigqueue, GLIBC_2_34);
