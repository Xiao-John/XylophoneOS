/* SPDX-License-Identifier: Apache-2.0 */
#include "xos_timer.h"
int
__timer_create (clockid_t clock, struct sigevent *event, timer_t *timer)
{
  return __xos_timer_create (clock, event, timer);
}
weak_alias (__timer_create, timer_create)
