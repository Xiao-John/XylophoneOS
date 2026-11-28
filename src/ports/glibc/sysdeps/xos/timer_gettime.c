/* SPDX-License-Identifier: Apache-2.0 */
#include "xos_timer.h"
int
__timer_gettime (timer_t timer, struct itimerspec *value)
{
  return __xos_timer_gettime (timer, value);
}
weak_alias (__timer_gettime, timer_gettime)
