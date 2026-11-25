/* SPDX-License-Identifier: Apache-2.0
   Native signal/timer delivery is outside the static glibc profile. */
#include <errno.h>
#include <signal.h>
#include <time.h>
int
__timer_delete (timer_t timer)
{
  (void) timer;
  __set_errno (ENOSYS);
  return -1;
}
weak_alias (__timer_delete, timer_delete)
stub_warning (timer_delete)
