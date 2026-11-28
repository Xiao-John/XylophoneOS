/* SPDX-License-Identifier: Apache-2.0 */
#define _GNU_SOURCE 1
#include <errno.h>
#include <pthread.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#define REQUIRE(test) do { if (!(test)) { \
  printf ("TIMER_THREAD_FAIL line=%d errno=%d\n", __LINE__, errno); exit (1); \
} } while (0)
struct native_thread_stats
{
  uint32_t version, size;
  uint64_t reserved_header;
  uint32_t processes, threads, reserved, waiting, results, free_pages;
  uint32_t process_user_pages, process_kernel_stack_pages;
};
static struct native_thread_stats thread_stats (void)
{
  struct native_thread_stats value;
  long result;
  __asm__ volatile ("int $0x80" : "=a" (result)
                    : "a" (50UL), "D" (&value), "S" (0UL), "d" (0UL)
                    : "memory", "cc");
  REQUIRE (result == 0 && value.version == 1 && value.size == sizeof value);
  return value;
}
static uint64_t now (void)
{
  struct timespec value;
  REQUIRE (clock_gettime (CLOCK_MONOTONIC, &value) == 0);
  return (uint64_t) value.tv_sec * 1000000000 + value.tv_nsec;
}
static void pause_ms (unsigned milliseconds)
{
#ifdef XOS_TIMER_NATIVE_SLEEP
  /* Explicit synchronization for staging against the old sleep stub. */
  uint64_t deadline = now () + (uint64_t) milliseconds * 1000000;
  long status;
  __asm__ volatile ("int $0x80" : "=a" (status)
                    : "a" (47UL), "D" (deadline), "S" (0UL), "d" (0UL)
                    : "memory", "cc");
  REQUIRE (status == 0);
#else
  struct timespec delay = {milliseconds / 1000, (milliseconds % 1000) * 1000000};
  REQUIRE (nanosleep (&delay, NULL) == 0);
#endif
}
static unsigned calls, finished, release_callback, release_peer, destructor_entered;
static unsigned release_destructor, destructor_done, active, max_active;
static timer_t timer, second;
static pthread_key_t key;
static int recorded_overrun;
static unsigned mode;
static size_t expected_stack = 256 * 1024;

static void wait_at_least (unsigned *word, unsigned expected)
{
  uint64_t deadline = now () + 3000000000ULL;
  while (__atomic_load_n (word, __ATOMIC_ACQUIRE) < expected)
    {
      REQUIRE (now () < deadline);
      pause_ms (10);
    }
}
static void wait_threads (unsigned expected)
{
  uint64_t deadline = now () + 3000000000ULL;
  for (;;)
    {
      struct native_thread_stats state = thread_stats ();
      if (state.threads == expected && state.reserved == 0 && state.results == 0)
        return;
      REQUIRE (now () < deadline);
      pause_ms (10);
    }
}
static void arm (timer_t target, unsigned first_ms, unsigned interval_ms)
{
  struct itimerspec value = {
    {interval_ms / 1000, (interval_ms % 1000) * 1000000},
    {first_ms / 1000, (first_ms % 1000) * 1000000}
  };
  REQUIRE (timer_settime (target, 0, &value, NULL) == 0);
}
static void destructor (void *value)
{
  REQUIRE (value == &key);
  __atomic_store_n (&destructor_entered, 1, __ATOMIC_RELEASE);
  wait_at_least (&release_destructor, 1);
  __atomic_store_n (&destructor_done, 1, __ATOMIC_RELEASE);
}
static void callback (union sigval value)
{
  REQUIRE (value.sival_int == 123);
  unsigned current = __atomic_add_fetch (&active, 1, __ATOMIC_ACQ_REL);
  REQUIRE (current == 1);
  __atomic_store_n (&max_active, current, __ATOMIC_RELEASE);
  pthread_attr_t attributes;
  REQUIRE (pthread_getattr_np (pthread_self (), &attributes) == 0);
  size_t stack;
  int detached;
  REQUIRE (pthread_attr_getstacksize (&attributes, &stack) == 0 && stack == expected_stack);
  REQUIRE (pthread_attr_getdetachstate (&attributes, &detached) == 0
           && detached == PTHREAD_CREATE_DETACHED);
  REQUIRE (pthread_attr_destroy (&attributes) == 0);
  unsigned count = __atomic_add_fetch (&calls, 1, __ATOMIC_ACQ_REL);
  if (mode == 1)
    REQUIRE (timer_delete (timer) == 0); /* Callback can delete itself. */
  else if (mode == 2)
    {
      if (count == 1) wait_at_least (&release_callback, 1);
      else
        {
          recorded_overrun = timer_getoverrun (timer);
          REQUIRE (recorded_overrun >= 2);
          arm (timer, 0, 0);
        }
    }
  else if (mode == 3)
    {
      if (count == 1)
        {
          REQUIRE (pthread_setspecific (key, &key) == 0);
          __atomic_sub_fetch (&active, 1, __ATOMIC_RELEASE);
          pthread_exit (NULL);
        }
      REQUIRE (__atomic_load_n (&destructor_done, __ATOMIC_ACQUIRE) == 1);
    }
  else if (mode == 4)
    wait_at_least (&release_callback, 1);
  else if (mode == 5)
    {
      recorded_overrun = timer_getoverrun (timer);
      REQUIRE (recorded_overrun >= 2);
      arm (timer, 0, 0);
    }
  __atomic_sub_fetch (&active, 1, __ATOMIC_RELEASE);
  __atomic_add_fetch (&finished, 1, __ATOMIC_RELEASE);
}
static timer_t create_timer (pthread_attr_t *attributes)
{
  struct sigevent event = {.sigev_notify = SIGEV_THREAD,
    .sigev_notify_function = callback, .sigev_value.sival_int = 123,
    .sigev_notify_attributes = attributes};
  timer_t created;
  REQUIRE (timer_create (CLOCK_MONOTONIC, &event, &created) == 0);
  return created;
}
static void *peer (void *unused)
{
  (void) unused;
  wait_at_least (&release_peer, 1);
  return NULL;
}
static void reset (unsigned selected_mode)
{
  wait_threads (1);
  mode = selected_mode;
  calls = finished = release_callback = release_peer = destructor_entered = 0;
  release_destructor = destructor_done = active = max_active = 0;
  expected_stack = 256 * 1024;
}
int main (void)
{
  struct native_thread_stats baseline = thread_stats ();
  reset (0);
  pthread_t occupied[3];
  for (unsigned i = 0; i < 3; ++i)
    REQUIRE (pthread_create (&occupied[i], NULL, peer, NULL) == 0);
  REQUIRE (thread_stats ().threads == 4);
  struct sigevent event = {.sigev_notify = SIGEV_THREAD,
    .sigev_notify_function = callback, .sigev_value.sival_int = 123};
  timer_t rejected = (timer_t) (uintptr_t) 77;
  REQUIRE (timer_create (CLOCK_MONOTONIC, &event, &rejected) == -1
           && errno == EAGAIN && rejected == (timer_t) (uintptr_t) 77);
  event.sigev_notify = SIGEV_NONE;
  REQUIRE (timer_create (CLOCK_MONOTONIC, &event, &timer) == 0);
  REQUIRE (timer_delete (timer) == 0); /* NONE still needs no worker slot. */
  __atomic_store_n (&release_peer, 1, __ATOMIC_RELEASE);
  for (unsigned i = 0; i < 3; ++i) REQUIRE (pthread_join (occupied[i], NULL) == 0);
  wait_threads (1);
  puts ("TIMER_THREAD_PASS scheduler_quota_failure_rollback_none_available");
  reset (1);
  timer = create_timer (NULL);
  arm (timer, 2000, 0);
  pause_ms (20);
  uint64_t began = now ();
  arm (timer, 20, 0); /* Must wake the sleeping scheduler, not wait two seconds. */
  wait_at_least (&calls, 1);
  wait_threads (1);
  REQUIRE (now () - began < 1000000000ULL && max_active == 1);
  struct itimerspec value;
  REQUIRE (timer_gettime (timer, &value) == -1 && errno == EINVAL);
  puts ("TIMER_THREAD_PASS rearm_wakes_self_delete_default_stack");

  reset (2);
  timer = create_timer (NULL);
  arm (timer, 10, 20);
  wait_at_least (&calls, 1);
  pause_ms (130);
  REQUIRE (__atomic_load_n (&calls, __ATOMIC_ACQUIRE) == 1);
  __atomic_store_n (&release_callback, 1, __ATOMIC_RELEASE);
  wait_at_least (&finished, 2);
  REQUIRE (recorded_overrun >= 2 && max_active == 1);
  REQUIRE (timer_delete (timer) == 0);
  wait_threads (1);
  printf ("TIMER_THREAD_PASS bounded_callback_coalescing overrun=%d\n", recorded_overrun);

  reset (3);
  REQUIRE (pthread_key_create (&key, destructor) == 0);
  timer = create_timer (NULL);
  second = create_timer (NULL);
  arm (timer, 10, 0);
  wait_at_least (&destructor_entered, 1);
  arm (second, 10, 0);
  pause_ms (70);
  REQUIRE (__atomic_load_n (&calls, __ATOMIC_ACQUIRE) == 1);
  REQUIRE (thread_stats ().threads == 3); /* Main, scheduler, cleaning callback. */
  __atomic_store_n (&release_destructor, 1, __ATOMIC_RELEASE);
  wait_at_least (&calls, 2);
  REQUIRE (timer_delete (timer) == 0 && timer_delete (second) == 0);
  wait_threads (1);
  REQUIRE (pthread_key_delete (key) == 0 && destructor_done == 1);
  puts ("TIMER_THREAD_PASS pthread_exit_TSD_cleanup_before_next_callback");

  reset (4);
  timer = create_timer (NULL);
  arm (timer, 10, 0);
  wait_at_least (&calls, 1);
  timer_t old = timer;
  REQUIRE (timer_delete (timer) == 0);
  struct sigevent none = {.sigev_notify = SIGEV_NONE};
  REQUIRE (timer_create (CLOCK_MONOTONIC, &none, &timer) == 0 && timer != old);
  REQUIRE (timer_gettime (old, &value) == -1 && errno == EINVAL);
  __atomic_store_n (&release_callback, 1, __ATOMIC_RELEASE);
  wait_threads (1);
  REQUIRE (timer_gettime (timer, &value) == 0 && timer_delete (timer) == 0);
  puts ("TIMER_THREAD_PASS delete_reuse_with_committed_callback");

  reset (5);
  timer = create_timer (NULL);
  pthread_t peers[2];
  for (unsigned i = 0; i < 2; ++i)
    REQUIRE (pthread_create (&peers[i], NULL, peer, NULL) == 0);
  REQUIRE (thread_stats ().threads == 4);
  arm (timer, 10, 20);
  pause_ms (130);
  REQUIRE (__atomic_load_n (&calls, __ATOMIC_ACQUIRE) == 0);
  __atomic_store_n (&release_peer, 1, __ATOMIC_RELEASE);
  for (unsigned i = 0; i < 2; ++i) REQUIRE (pthread_join (peers[i], NULL) == 0);
  wait_at_least (&finished, 1);
  REQUIRE (recorded_overrun >= 2 && timer_delete (timer) == 0);
  wait_threads (1);
  printf ("TIMER_THREAD_PASS quota_retry_retains_notification overrun=%d\n", recorded_overrun);

  reset (1);
  pthread_attr_t attributes;
  REQUIRE (pthread_attr_init (&attributes) == 0);
  REQUIRE (pthread_attr_setstacksize (&attributes, 64 * 1024) == 0);
  expected_stack = 64 * 1024;
  timer = create_timer (&attributes);
  REQUIRE (pthread_attr_destroy (&attributes) == 0); /* Timer owns its copy. */
  arm (timer, 10, 0);
  wait_at_least (&calls, 1);
  wait_threads (1);
  struct native_thread_stats after = thread_stats ();
  REQUIRE (after.process_kernel_stack_pages == baseline.process_kernel_stack_pages);
  puts ("TIMER_THREAD_PASS explicit_stack_copy_and_native_resources");
  puts ("TIMER_THREAD_PASS complete");
  return 0;
}
