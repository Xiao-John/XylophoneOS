/* SPDX-License-Identifier: Apache-2.0 */
#include "xos_timer.h"
int
__timer_delete (timer_t timer)
{
  return __xos_timer_delete (timer);
}
weak_alias (__timer_delete, timer_delete)
