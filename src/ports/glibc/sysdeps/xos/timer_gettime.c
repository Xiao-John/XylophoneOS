/* SPDX-License-Identifier: Apache-2.0
   Native signal/timer delivery is outside the static glibc profile. */
#include <errno.h>
#include <signal.h>
#include <time.h>
int
__timer_gettime (timer_t timer, struct itimerspec *value)
{
  (void) timer; (void) value;
  __set_errno (ENOSYS);
  return -1;
}
weak_alias (__timer_gettime, timer_gettime)
stub_warning (timer_gettime)
