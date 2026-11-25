/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <pthreadP.h>
#include <signal.h>
#include <shlib-compat.h>

int
__pthread_sigmask (int how, const sigset_t *mask, sigset_t *previous)
{
  if (mask != NULL && how != SIG_BLOCK && how != SIG_UNBLOCK
      && how != SIG_SETMASK)
    return EINVAL;
  if (mask == NULL && previous == NULL)
    return 0;
  /* XOS has no signal mask to update or copy out. */
  return ENOTSUP;
}
libc_hidden_def (__pthread_sigmask)
versioned_symbol (libc, __pthread_sigmask, pthread_sigmask, GLIBC_2_32);
