/* SPDX-License-Identifier: Apache-2.0 */
#include "xos_timer.h"
int
__timer_getoverrun (timer_t timer)
{
  return __xos_timer_getoverrun (timer);
}
weak_alias (__timer_getoverrun, timer_getoverrun)
