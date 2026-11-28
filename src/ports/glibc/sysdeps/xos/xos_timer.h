/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_GLIBC_TIMER_H
#define XOS_GLIBC_TIMER_H 1
#include <signal.h>
#include <time.h>

int __xos_timer_create (clockid_t, const struct sigevent *, timer_t *)
  __attribute__ ((visibility ("hidden")));
int __xos_timer_delete (timer_t) __attribute__ ((visibility ("hidden")));
int __xos_timer_settime (timer_t, int, const struct itimerspec *,
                         struct itimerspec *)
  __attribute__ ((visibility ("hidden")));
int __xos_timer_gettime (timer_t, struct itimerspec *)
  __attribute__ ((visibility ("hidden")));
int __xos_timer_getoverrun (timer_t) __attribute__ ((visibility ("hidden")));
/* POSIX timers are not inherited. Called before child atfork handlers. */
void __xos_timer_after_fork (void) __attribute__ ((visibility ("hidden")));
#endif
