/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <pthreadP.h>
#include <signal.h>
#include <shlib-compat.h>
#include "xos_thread_name.h"

int
__pthread_raise_internal (int signal)
{
  if (signal < 0 || signal >= _NSIG)
    return EINVAL;
  return signal == 0 ? 0 : ENOTSUP;
}

int
__pthread_kill_internal (pthread_t thread, int signal)
{
  if (signal < 0 || signal >= _NSIG)
    return EINVAL;
  if (thread != __pthread_self () && !__xos_thread_registered (thread))
    return ESRCH;
  /* No asynchronous thread-directed delivery exists in the XOS ABI.
     Signal zero only checks the calling or a registered live thread. */
  return signal == 0 ? 0 : ENOTSUP;
}

int
__pthread_kill (pthread_t thread, int signal)
{
  if (is_internal_signal (signal))
    return EINVAL;
  return __pthread_kill_internal (thread, signal);
}

#if !IS_IN (rtld)
libc_hidden_def (__pthread_kill)
versioned_symbol (libc, __pthread_kill, pthread_kill, GLIBC_2_34);
#endif
