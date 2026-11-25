/* SPDX-License-Identifier: Apache-2.0 */
#include <limits.h>
#include <pthreadP.h>
#include "xos_thread_name.h"

pid_t
pthread_gettid_np (pthread_t thread)
{
  /* Public handles are native TIDs, never descriptor addresses. The
     registry is removed before the kernel releases a worker's TLS. */
  if (thread == 0 || thread > INT_MAX
      || (thread != __pthread_self () && !__xos_thread_registered (thread)))
    return -1;
  return (pid_t) thread;
}
