/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <pthreadP.h>

int
__pthread_setschedparam (pthread_t thread, int policy,
                         const struct sched_param *param)
{
  /* XOS does not expose per-thread scheduling parameters. */
  (void) thread;
  (void) policy;
  (void) param;
  return ENOTSUP;
}
strong_alias (__pthread_setschedparam, pthread_setschedparam)
