/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <pthreadP.h>

int
__pthread_getschedparam (pthread_t thread, int *policy, struct sched_param *param)
{
  /* XOS does not expose per-thread scheduling parameters. */
  (void) thread;
  (void) policy;
  (void) param;
  return ENOTSUP;
}
libc_hidden_def (__pthread_getschedparam)
strong_alias (__pthread_getschedparam, pthread_getschedparam)
