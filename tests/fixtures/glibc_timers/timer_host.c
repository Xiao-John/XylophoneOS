/* SPDX-License-Identifier: Apache-2.0
   The fake platform stops a scheduler at its blocking wait. It never
   implements a timer; all handles/deadlines/coalescing are production code. */
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <pthreadP.h>
#include <setjmp.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "xos_timer.h"
#include "xos_wait_word.h"

static uint64_t mono = 100, wall = 1000;
static int wall_failed, quota_failed;
static jmp_buf blocked;
static int may_block;
static uint64_t last_deadline;
struct worker { void *(*function)(void *); void *argument; int alive; };
static struct worker workers[64];
static unsigned created, callback_value, callbacks;

int timer_test_attr_init (pthread_attr_t *a) { memset(a, 0, sizeof *a); return 0; }
int timer_test_attr_copy (pthread_attr_t *a, const pthread_attr_t *b) { *a = *b; return 0; }
int timer_test_attr_size (pthread_attr_t *a, size_t size)
{ ((struct pthread_attr *) a)->stacksize = size; return 0; }
int timer_test_attr_detach (pthread_attr_t *a, int mode)
{ (void) a; assert(mode == PTHREAD_CREATE_DETACHED); return 0; }
int timer_test_attr_destroy (pthread_attr_t *a) { (void) a; return 0; }
int timer_test_create (pthread_t *tid, const pthread_attr_t *attributes,
                      void *(*function)(void *), void *argument)
{
  (void) attributes;
  if (quota_failed) return EAGAIN;
  assert(++created < 64);
  workers[created] = (struct worker) {function, argument, 1};
  *tid = created;
  return 0;
}
long __xos_clock_test_trap (unsigned long number, unsigned long first)
{
  assert(first == 0 && (number == 46 || number == 64));
  return number == 46 ? (long) mono : wall_failed ? -5 : (long) wall;
}
xos_i64 __xos_thread_identity_test_call (xos_u64 number, xos_u64 tid, xos_u64 second)
{
  assert(number == 45 && tid > 0 && tid <= created && second == 0);
  return workers[tid].alive ? -2 : -15;
}
xos_i64 __xos_wait_word (xos_u32 *address, xos_u32 expected, xos_u64 deadline)
{
  assert(may_block && *address == expected);
  last_deadline = deadline;
  longjmp(blocked, 1);
}
xos_i64 __xos_wake_word (xos_u32 *address, xos_u32 count)
{ (void) address; assert(count == 1); return 0; }
void __libc_fatal (const char *message) { fputs(message, stderr); abort(); }
static void schedule (unsigned tid)
{
  may_block = 1;
  if (setjmp(blocked) == 0)
    {
      workers[tid].function(workers[tid].argument);
      workers[tid].alive = 0;
    }
  may_block = 0;
}
static void complete (unsigned tid)
{
  workers[tid].function(workers[tid].argument);
  /* Deliberately retain the native TID to model cleanup after this handler. */
}
static void callback (union sigval value)
{ callback_value = value.sival_int; ++callbacks; }
static struct itimerspec at (uint64_t initial, uint64_t interval)
{
  return (struct itimerspec) {
    {interval / 1000000000, interval % 1000000000},
    {initial / 1000000000, initial % 1000000000}
  };
}
int main (void)
{
  struct sigevent none = {.sigev_notify = SIGEV_NONE};
  timer_t timer;
  assert(__xos_timer_create(CLOCK_REALTIME, &none, &timer) == 0 && created == 0);
  struct itimerspec value = at(50, 20), result;
  assert(__xos_timer_settime(timer, 0, &value, NULL) == 0);
  mono += 10; wall += 10000000;
  assert(__xos_timer_gettime(timer, &result) == 0 && result.it_value.tv_nsec == 40);
  wall -= 10000000;
  mono = 190;
  assert(__xos_timer_gettime(timer, &result) == 0 && result.it_value.tv_nsec == 20);
  value = at(1100, 0);
  assert(__xos_timer_settime(timer, TIMER_ABSTIME, &value, NULL) == 0);
  wall = 1101;
  assert(__xos_timer_gettime(timer, &result) == 0 && result.it_value.tv_nsec == 0);
  wall_failed = 1;
  result = at(99, 88);
  assert(__xos_timer_gettime(timer, &result) == -1 && errno == EIO
         && result.it_value.tv_nsec == 99);
  wall_failed = 0;
  value = at(INT64_MAX, 0);
  assert(__xos_timer_settime(timer, 0, &value, NULL) == -1 && errno == EOVERFLOW);
  assert(__xos_timer_delete(timer) == 0);
  puts("TIMER_HOST_PASS time_domains_phase_overflow_failure_atomicity");

  struct sigevent event = {.sigev_notify = SIGEV_THREAD,
    .sigev_notify_function = callback, .sigev_value.sival_int = 17};
  quota_failed = 1;
  timer = (timer_t) (uintptr_t) 77;
  assert(__xos_timer_create(CLOCK_MONOTONIC, &event, &timer) == -1
         && errno == EAGAIN && timer == (timer_t) (uintptr_t) 77 && created == 0);
  quota_failed = 0;
  assert(__xos_timer_create(CLOCK_MONOTONIC, &event, &timer) == 0 && created == 1);
  unsigned scheduler = created;
  value = at(10, 10);
  assert(__xos_timer_settime(timer, 0, &value, NULL) == 0);
  quota_failed = 1;
  mono += 55;
  schedule(scheduler);
  assert(created == 1 && callbacks == 0 && last_deadline > mono);
  mono += 30;
  quota_failed = 0;
  schedule(scheduler);
  assert(created == 2 && __xos_timer_getoverrun(timer) == 7);
  complete(2);
  assert(callbacks == 1 && callback_value == 17);
  mono += 45;
  schedule(scheduler);
  assert(created == 2); /* Handler finished, but native/TLS cleanup has not. */
  workers[2].alive = 0;
  schedule(scheduler);
  assert(created == 3 && __xos_timer_getoverrun(timer) == 4);
  assert(__xos_timer_delete(timer) == 0);
  timer_t old = timer;
  event.sigev_value.sival_int = 91;
  assert(__xos_timer_create(CLOCK_MONOTONIC, &event, &timer) == 0 && timer != old);
  assert(__xos_timer_getoverrun(old) == -1 && errno == EINVAL);
  complete(3);
  assert(callbacks == 2 && callback_value == 17); /* Committed copy survives reuse. */
  workers[3].alive = 0;
  schedule(scheduler);
  puts("TIMER_HOST_PASS quota_retention_exact_overrun_reap_and_committed_copy");

  value = at(1, 1);
  assert(__xos_timer_settime(timer, 0, &value, NULL) == 0);
  mono += (uint64_t) INT_MAX + 100;
  schedule(scheduler);
  assert(created == 4 && __xos_timer_getoverrun(timer) == INT_MAX);
  complete(4); workers[4].alive = 0;
  value = at(0, 0);
  assert(__xos_timer_settime(timer, 0, &value, NULL) == 0);
  assert(__xos_timer_getoverrun(timer) == 0);
  assert(__xos_timer_delete(timer) == 0);
  schedule(scheduler);
  assert(workers[scheduler].alive == 0);
  assert(__xos_timer_create(CLOCK_MONOTONIC, &none, &timer) == 0);
  old = timer;
  __xos_timer_after_fork();
  assert(__xos_timer_gettime(old, &result) == -1 && errno == EINVAL);
  assert(__xos_timer_create(CLOCK_MONOTONIC, &none, &timer) == 0 && timer != old);
  assert(__xos_timer_delete(timer) == 0);
  puts("TIMER_HOST_PASS overrun_saturation_disarm_scheduler_exit_fork_reset");
}
