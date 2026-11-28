/* SPDX-License-Identifier: Apache-2.0
   Process-local POSIX timer subset. No kernel timer objects or signals.

   NONE timers need no worker. THREAD timers share one sleeping scheduler
   and at most one detached callback, including its native cleanup. Slots
   are generation handles; a committed callback owns copies, never a slot.
   All mutable state is protected by timer_lock. */
#include <errno.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <pthreadP.h>
#include <libc-internal.h>
#include "xos_timer.h"
#include "xos_clock.h"
#include "xos_thread_identity.h"

#ifndef XOS_TIMER_CAPACITY
# define XOS_TIMER_CAPACITY 32
#endif
_Static_assert (XOS_TIMER_CAPACITY > 0 && XOS_TIMER_CAPACITY <= 255,
                "private timer pool capacity");
/* The native clock returns a signed non-negative nanosecond count. */
#define TIMER_NS_MAX ((uint64_t) INT64_MAX)
#define TIMER_PENDING_MAX ((uint64_t) INT_MAX + 1)
#define TIMER_RETRY_NS 10000000ULL

struct timer_slot
{
  uintptr_t generation;
  int used, notify, overrun;
  clockid_t clock, deadline_clock;
  uint64_t deadline, interval, pending;
  int armed;
  void (*function) (union sigval);
  union sigval value;
  pthread_attr_t attributes;
};

static struct timer_slot timer_slots[XOS_TIMER_CAPACITY];
static xos_u32 timer_lock, timer_sequence;
static pthread_t scheduler_tid, callback_tid;
static int scheduler_running, callback_done;
static unsigned dispatch_cursor;
static void (*callback_function) (union sigval);
static union sigval callback_value;

static void
lock_timers (void)
{
  while (__atomic_exchange_n (&timer_lock, 1, __ATOMIC_ACQUIRE))
    __xos_wait_word (&timer_lock, 1, UINT64_MAX);
}

static void
unlock_timers (void)
{
  __atomic_store_n (&timer_lock, 0, __ATOMIC_RELEASE);
  __xos_wake_word (&timer_lock, 1);
}

static void
changed (void)
{
  __atomic_add_fetch (&timer_sequence, 1, __ATOMIC_RELEASE);
  __xos_wake_word (&timer_sequence, 1);
}

static int
error_result (int error)
{
  __set_errno (error);
  return -1;
}

static int
read_clock (clockid_t clock, uint64_t *now)
{
  long result = __xos_clock_trap (clock == CLOCK_MONOTONIC ? 46 : 64, 0);
  if (result < 0)
    return clock == CLOCK_MONOTONIC ? EOVERFLOW : EIO;
  *now = (uint64_t) result;
  return 0;
}

static int
to_ns (const struct timespec *time, uint64_t *ns)
{
  if (time->tv_sec < 0 || time->tv_nsec < 0 || time->tv_nsec >= 1000000000)
    return EINVAL;
  if ((uint64_t) time->tv_sec > TIMER_NS_MAX / 1000000000
      || (uint64_t) time->tv_sec * 1000000000
           > TIMER_NS_MAX - (uint64_t) time->tv_nsec)
    return EOVERFLOW;
  *ns = (uint64_t) time->tv_sec * 1000000000 + time->tv_nsec;
  return 0;
}

static struct timespec
from_ns (uint64_t ns)
{
  return (struct timespec) { ns / 1000000000, ns % 1000000000 };
}

static struct timer_slot *
lookup (timer_t handle)
{
  uintptr_t encoded = (uintptr_t) handle;
  unsigned index = encoded & 255;
  if (index == 0 || index > XOS_TIMER_CAPACITY || (encoded >> 8) == 0)
    return NULL;
  struct timer_slot *slot = &timer_slots[index - 1];
  return slot->used && slot->generation == (encoded >> 8) ? slot : NULL;
}

/* Advance against the original phase, not the late observer's timestamp. */
static void
expire (struct timer_slot *slot, uint64_t now)
{
  if (!slot->armed || now < slot->deadline)
    return;
  uint64_t count = 1;
  if (slot->interval != 0)
    {
      count += (now - slot->deadline) / slot->interval;
      if (count > (TIMER_NS_MAX - slot->deadline) / slot->interval)
        slot->armed = 0;
      else
        slot->deadline += count * slot->interval;
    }
  else
    slot->armed = 0;
  if (slot->notify == SIGEV_THREAD)
    slot->pending = count >= TIMER_PENDING_MAX - slot->pending
      ? TIMER_PENDING_MAX : slot->pending + count;
}

static int
snapshot (struct timer_slot *slot, struct itimerspec *output)
{
  uint64_t now;
  int error = read_clock (slot->deadline_clock, &now);
  if (error != 0)
    return error;
  expire (slot, now);
  output->it_interval = from_ns (slot->interval);
  output->it_value = from_ns (slot->armed ? slot->deadline - now : 0);
  return 0;
}

/* pthread_create's existing XOS policy, validated before publishing a timer.
   Copy owned attributes, not a pointer to caller memory or its extensions. */
static int
copy_attributes (pthread_attr_t *output, const pthread_attr_t *input)
{
  int error, initialized = 0;
  if (input == NULL)
    {
      error = __pthread_attr_init (output);
      if (error == 0)
        {
          initialized = 1;
          error = __pthread_attr_setstacksize (output, 256 * 1024);
        }
    }
  else
    {
      const struct pthread_attr *a = (const struct pthread_attr *) input;
      if ((a->flags & (ATTR_FLAG_STACKADDR | ATTR_FLAG_NOTINHERITSCHED
                      | ATTR_FLAG_SCOPEPROCESS | ATTR_FLAG_DO_RSEQ)) != 0
          || (a->extension != NULL
              && (a->extension->cpuset != NULL || a->extension->sigmask_set))
          || a->guardsize > 0xe0000)
        return ENOTSUP;
      size_t size = a->stacksize == 0 ? 256 * 1024 : a->stacksize;
      if (size < 64 * 1024 || size > 2 * 1024 * 1024)
        return EINVAL;
      error = __pthread_attr_copy (output, input);
      if (error == 0)
        {
          initialized = 1;
          error = __pthread_attr_setstacksize (output, size);
        }
    }
  if (error == 0)
    error = __pthread_attr_setdetachstate (output, PTHREAD_CREATE_DETACHED);
  if (error != 0 && initialized)
    __pthread_attr_destroy (output);
  return error;
}

static void
callback_finished (void *unused)
{
  (void) unused;
  lock_timers ();
  callback_done = 1;
  changed ();
  unlock_timers ();
}

static void *
run_callback (void *unused)
{
  (void) unused;
  /* The scheduler will not overwrite these until this detached TID has
     disappeared from the native lifecycle table, after all TLS cleanup. */
  void (*function) (union sigval) = callback_function;
  union sigval value = callback_value;
  pthread_cleanup_push (callback_finished, NULL);
  function (value);
  pthread_cleanup_pop (1);
  return NULL;
}

/* A detached ID is never reused. Detach on this known-detached TID cannot
   mutate it: invalid means still alive/cleaning, not_found means reaped.
   This closes the gap between the callback cleanup handler and native exit
   without adding an ABI or retaining a pointer to its freed stack/TCB. */
static int
detached_reaped (pthread_t tid)
{
  long status = xos_thread_lifecycle (45, (xos_u64) tid, 0);
  if (status == -15)
    return 1;
  if (status != -2)
    __libc_fatal ("XOS timer: detached worker lifecycle mismatch\n");
  return 0;
}

static uint64_t
retry_deadline (uint64_t now)
{
  return now > TIMER_NS_MAX - TIMER_RETRY_NS
    ? TIMER_NS_MAX : now + TIMER_RETRY_NS;
}

static void *
run_scheduler (void *unused)
{
  (void) unused;
  for (;;)
    {
      lock_timers ();
      uint64_t monotonic = 0, realtime = 0;
      int monotonic_error = read_clock (CLOCK_MONOTONIC, &monotonic);
      int realtime_error = read_clock (CLOCK_REALTIME, &realtime);
      uint64_t deadline = UINT64_MAX;
      int thread_timers = 0;

      if (callback_tid != 0 && callback_done && detached_reaped (callback_tid))
        {
          callback_tid = 0;
          callback_done = 0;
        }

      for (unsigned i = 0; i < XOS_TIMER_CAPACITY; ++i)
        {
          struct timer_slot *slot = &timer_slots[i];
          if (!slot->used || slot->notify != SIGEV_THREAD)
            continue;
          thread_timers = 1;
          int error = slot->deadline_clock == CLOCK_MONOTONIC
            ? monotonic_error : realtime_error;
          uint64_t now = slot->deadline_clock == CLOCK_MONOTONIC
            ? monotonic : realtime;
          if (error == 0)
            expire (slot, now);
          if (slot->armed && error == 0 && monotonic_error == 0)
            {
              uint64_t remaining = slot->deadline - now;
              uint64_t next = remaining > TIMER_NS_MAX - monotonic
                ? TIMER_NS_MAX : monotonic + remaining;
              if (next < deadline)
                deadline = next;
              /* Re-evaluate absolute realtime timers after clock changes.
                 Relative realtime timers use monotonic elapsed time. */
              if (slot->deadline_clock == CLOCK_REALTIME
                  && retry_deadline (monotonic) < deadline)
                deadline = retry_deadline (monotonic);
            }
          if ((error != 0 || slot->pending != 0) && monotonic_error == 0
              && retry_deadline (monotonic) < deadline)
            deadline = retry_deadline (monotonic);
        }

      if (callback_tid == 0)
        for (unsigned step = 0; step < XOS_TIMER_CAPACITY; ++step)
          {
            unsigned i = (dispatch_cursor + step) % XOS_TIMER_CAPACITY;
            struct timer_slot *slot = &timer_slots[i];
            if (!slot->used || slot->notify != SIGEV_THREAD || slot->pending == 0)
              continue;
            callback_function = slot->function;
            callback_value = slot->value;
            pthread_t tid;
            int error = __pthread_create (&tid, &slot->attributes, run_callback, NULL);
            if (error == 0)
              {
                callback_tid = tid;
                callback_done = 0;
                slot->overrun = (int) (slot->pending - 1);
                slot->pending = 0;
                dispatch_cursor = (i + 1) % XOS_TIMER_CAPACITY;
              }
            /* Quota exhaustion preserves the coalesced notification. A
               bounded sleeping retry never starts an unbounded worker set. */
            break;
          }

      if (!thread_timers && callback_tid == 0)
        {
          scheduler_running = 0;
          unlock_timers ();
          return NULL;
        }
      if (callback_tid != 0 && callback_done && monotonic_error == 0
          && retry_deadline (monotonic) < deadline)
        deadline = retry_deadline (monotonic);
      xos_u32 expected = __atomic_load_n (&timer_sequence, __ATOMIC_ACQUIRE);
      unlock_timers ();
      /* The native monotonic clock is required by all XOS waits. If it
         ceases to be representable, continuing to schedule is unsafe. */
      if (monotonic_error != 0)
        __libc_fatal ("XOS timer: monotonic clock unavailable\n");
      __xos_wait_word (&timer_sequence, expected, deadline);
    }
}

int
__xos_timer_create (clockid_t clock, const struct sigevent *event, timer_t *timer)
{
  if (clock != CLOCK_MONOTONIC && clock != CLOCK_REALTIME)
    return error_result (clock == CLOCK_PROCESS_CPUTIME_ID
                         || clock == CLOCK_THREAD_CPUTIME_ID ? ENOTSUP : EINVAL);
  if (event == NULL || event->sigev_notify == SIGEV_SIGNAL)
    return error_result (ENOTSUP);
  if (event->sigev_notify != SIGEV_NONE && event->sigev_notify != SIGEV_THREAD)
    return error_result (EINVAL);
  if (timer == NULL || (event->sigev_notify == SIGEV_THREAD
                        && event->sigev_notify_function == NULL))
    return error_result (EINVAL);
  uint64_t now;
  int error = read_clock (clock, &now);
  if (error != 0)
    return error_result (error);
  pthread_attr_t attributes;
  if (event->sigev_notify == SIGEV_THREAD)
    {
      error = copy_attributes (&attributes, event->sigev_notify_attributes);
      if (error != 0)
        return error_result (error);
    }

  lock_timers ();
  unsigned index;
  for (index = 0; index < XOS_TIMER_CAPACITY; ++index)
    if (!timer_slots[index].used
        && timer_slots[index].generation < (UINTPTR_MAX >> 8))
      break;
  if (index == XOS_TIMER_CAPACITY)
    error = EAGAIN;
  if (error == 0 && event->sigev_notify == SIGEV_THREAD && !scheduler_running)
    {
      if (scheduler_tid != 0 && !detached_reaped (scheduler_tid))
        error = EAGAIN;
      else
        {
          pthread_attr_t scheduler_attributes;
          error = copy_attributes (&scheduler_attributes, NULL);
          if (error == 0)
            {
              error = __pthread_create (&scheduler_tid, &scheduler_attributes,
                                         run_scheduler, NULL);
              __pthread_attr_destroy (&scheduler_attributes);
            }
          if (error == 0)
            scheduler_running = 1;
        }
    }
  if (error == 0)
    {
      struct timer_slot *slot = &timer_slots[index];
      uintptr_t generation = slot->generation + 1;
      memset (slot, 0, sizeof (*slot));
      slot->generation = generation;
      slot->used = 1;
      slot->notify = event->sigev_notify;
      slot->clock = slot->deadline_clock = clock;
      if (event->sigev_notify == SIGEV_THREAD)
        {
          slot->function = event->sigev_notify_function;
          slot->value = event->sigev_value;
          slot->attributes = attributes;
        }
      *timer = (timer_t) ((generation << 8) | (index + 1));
      changed ();
    }
  unlock_timers ();
  if (error != 0 && event->sigev_notify == SIGEV_THREAD)
    __pthread_attr_destroy (&attributes);
  return error == 0 ? 0 : error_result (error);
}

int
__xos_timer_delete (timer_t timer)
{
  lock_timers ();
  struct timer_slot *slot = lookup (timer);
  if (slot == NULL)
    {
      unlock_timers ();
      return error_result (EINVAL);
    }
  if (slot->notify == SIGEV_THREAD)
    __pthread_attr_destroy (&slot->attributes);
  slot->used = 0;
  changed ();
  unlock_timers ();
  return 0;
}

int
__xos_timer_settime (timer_t timer, int flags, const struct itimerspec *value,
                     struct itimerspec *old)
{
  if (value == NULL || (flags & ~TIMER_ABSTIME) != 0)
    return error_result (EINVAL);
  /* Accept value == old without observing our own output writes. */
  struct itimerspec input = *value, previous;
  uint64_t initial, interval;
  int error = to_ns (&input.it_value, &initial);
  if (error == 0)
    error = to_ns (&input.it_interval, &interval);
  if (error != 0)
    return error_result (error);
  lock_timers ();
  struct timer_slot *slot = lookup (timer);
  if (slot == NULL)
    error = EINVAL;
  uint64_t now = 0;
  clockid_t deadline_clock = slot != NULL && (flags & TIMER_ABSTIME)
    ? slot->clock : CLOCK_MONOTONIC;
  if (error == 0)
    error = read_clock (deadline_clock, &now);
  if (error == 0 && !(flags & TIMER_ABSTIME) && initial > TIMER_NS_MAX - now)
    error = EOVERFLOW;
  if (error == 0 && old != NULL)
    error = snapshot (slot, &previous);
  if (error == 0)
    {
      slot->deadline_clock = deadline_clock;
      slot->deadline = flags & TIMER_ABSTIME ? initial : now + initial;
      slot->interval = interval;
      slot->armed = initial != 0;
      slot->pending = 0;
      slot->overrun = 0;
      if (old != NULL)
        *old = previous;
      changed ();
    }
  unlock_timers ();
  return error == 0 ? 0 : error_result (error);
}

int
__xos_timer_gettime (timer_t timer, struct itimerspec *value)
{
  if (value == NULL)
    return error_result (EINVAL);
  lock_timers ();
  struct timer_slot *slot = lookup (timer);
  struct itimerspec result;
  int error = slot == NULL ? EINVAL : snapshot (slot, &result);
  if (error == 0)
    {
      *value = result;
      if (slot->pending != 0)
        changed ();
    }
  unlock_timers ();
  return error == 0 ? 0 : error_result (error);
}

int
__xos_timer_getoverrun (timer_t timer)
{
  lock_timers ();
  struct timer_slot *slot = lookup (timer);
  int result = slot == NULL ? -1 : slot->overrun;
  unlock_timers ();
  return result < 0 ? error_result (EINVAL) : result;
}

void
__xos_timer_after_fork (void)
{
  /* Native fork only admits a single-threaded process. No scheduler or
     callback can exist here; retaining generations rejects parent handles. */
  for (unsigned i = 0; i < XOS_TIMER_CAPACITY; ++i)
    timer_slots[i].used = 0;
  timer_lock = timer_sequence = 0;
  scheduler_tid = callback_tid = 0;
  scheduler_running = callback_done = 0;
}
