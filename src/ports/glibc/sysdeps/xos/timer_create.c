/* SPDX-License-Identifier: Apache-2.0
   Native signal/timer delivery is outside the static glibc profile. */
#include <errno.h>
#include <signal.h>
#include <time.h>
int
__timer_create (clockid_t clock, struct sigevent *event, timer_t *timer)
{
  (void) clock; (void) event; (void) timer;
  __set_errno (ENOSYS);
  return -1;
}
weak_alias (__timer_create, timer_create)
stub_warning (timer_create)
