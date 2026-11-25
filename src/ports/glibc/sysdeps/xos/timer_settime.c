/* SPDX-License-Identifier: Apache-2.0
   Native signal/timer delivery is outside the static glibc profile. */
#include <errno.h>
#include <signal.h>
#include <time.h>
int
__timer_settime (timer_t timer, int flags, const struct itimerspec *value, struct itimerspec *old)
{
  (void) timer; (void) flags; (void) value; (void) old;
  __set_errno (ENOSYS);
  return -1;
}
weak_alias (__timer_settime, timer_settime)
stub_warning (timer_settime)
