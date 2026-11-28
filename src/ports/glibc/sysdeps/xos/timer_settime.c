/* SPDX-License-Identifier: Apache-2.0 */
#include "xos_timer.h"
int
__timer_settime (timer_t timer, int flags, const struct itimerspec *value, struct itimerspec *old)
{
  return __xos_timer_settime (timer, flags, value, old);
}
weak_alias (__timer_settime, timer_settime)
