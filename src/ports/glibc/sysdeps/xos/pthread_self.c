/* SPDX-License-Identifier: Apache-2.0 */
#include <pthreadP.h>
#include "xos_thread_identity.h"

pthread_t
__pthread_self (void)
{
  struct xos_thread_info info;
  if (xos_thread_lifecycle (41, (xos_u64) &info, 0) != 0)
    __builtin_trap ();
  return (pthread_t) info.tid;
}
libc_hidden_def (__pthread_self)
weak_alias (__pthread_self, pthread_self)
