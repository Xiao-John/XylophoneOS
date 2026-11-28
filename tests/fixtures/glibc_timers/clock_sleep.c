/* SPDX-License-Identifier: Apache-2.0 */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <limits.h>
#include <pthread.h>
#include <semaphore.h>
#include <stdio.h>
#include <time.h>

#define REQUIRE(test) do { if (!(test)) { \
  printf ("CLOCK_SLEEP_FAIL line=%d errno=%d\n", __LINE__, errno); return 1; \
} } while (0)
static sem_t started;
static int worker_done;
static unsigned long now_ns (clockid_t clock)
{
  struct timespec value;
  if (clock_gettime (clock, &value) != 0) return ULONG_MAX;
  return (unsigned long) value.tv_sec * 1000000000UL + value.tv_nsec;
}
static struct timespec split_ns (unsigned long value)
{
  return (struct timespec) {value / 1000000000UL, value % 1000000000UL};
}
static void *worker (void *unused)
{
  (void) unused;
  if (sem_post (&started) != 0) return (void *) 1;
  struct timespec delay = {0, 10000000};
  if (nanosleep (&delay, NULL) != 0) return (void *) 2;
  __atomic_store_n (&worker_done, 1, __ATOMIC_RELEASE);
  return NULL;
}
int main (void)
{
  struct timespec delay = {0, 30000000}, remainder = {9, 8};
  unsigned long before = now_ns (CLOCK_MONOTONIC);
  REQUIRE (before != ULONG_MAX);
  errno = EDOM;
  REQUIRE (nanosleep (&delay, &remainder) == 0 && errno == EDOM);
  REQUIRE (now_ns (CLOCK_MONOTONIC) - before >= 30000000);
  REQUIRE (remainder.tv_sec == 9 && remainder.tv_nsec == 8);
  puts ("CLOCK_SLEEP_PASS relative_nanosleep");

  for (int index = 0; index < 2; ++index)
    {
      clockid_t clock = index == 0 ? CLOCK_MONOTONIC : CLOCK_REALTIME;
      unsigned long start = now_ns (clock);
      REQUIRE (start != ULONG_MAX && start < LONG_MAX - 30000000UL);
      struct timespec limit = split_ns (start + 30000000);
      REQUIRE (clock_nanosleep (clock, TIMER_ABSTIME, &limit, &remainder) == 0);
      REQUIRE (now_ns (clock) >= start + 30000000);
      limit = (struct timespec) {0, 1};
      REQUIRE (clock_nanosleep (clock, TIMER_ABSTIME, &limit, NULL) == 0);
    }
  puts ("CLOCK_SLEEP_PASS absolute_monotonic_realtime");

  errno = EDOM;
  delay = (struct timespec) {0, 1000000000L};
  REQUIRE (clock_nanosleep (CLOCK_MONOTONIC, 0, &delay, &remainder) == EINVAL);
  delay = (struct timespec) {-1, 0};
  REQUIRE (clock_nanosleep (CLOCK_MONOTONIC, 0, &delay, NULL) == EINVAL);
  delay = (struct timespec) {LONG_MAX, 0};
  REQUIRE (clock_nanosleep (CLOCK_MONOTONIC, 0, &delay, NULL) == EOVERFLOW);
  delay = (struct timespec) {0, 0};
  REQUIRE (clock_nanosleep (CLOCK_MONOTONIC, 2, &delay, NULL) == EINVAL);
  REQUIRE (clock_nanosleep (987, 0, &delay, NULL) == EINVAL);
  REQUIRE (clock_nanosleep (CLOCK_PROCESS_CPUTIME_ID, 0, &delay, NULL) == ENOTSUP);
  REQUIRE (clock_nanosleep (CLOCK_THREAD_CPUTIME_ID, 0, &delay, NULL) == ENOTSUP);
  REQUIRE (clock_nanosleep (CLOCK_REALTIME, 0, &delay, NULL) == 0 && errno == EDOM);
  REQUIRE (remainder.tv_sec == 9 && remainder.tv_nsec == 8);
  delay.tv_nsec = -1;
  REQUIRE (nanosleep (&delay, NULL) == -1 && errno == EINVAL);
  puts ("CLOCK_SLEEP_PASS invalid_overflow_error_number_errno");

  REQUIRE (sem_init (&started, 0, 0) == 0);
  pthread_t thread;
  REQUIRE (pthread_create (&thread, NULL, worker, NULL) == 0);
  REQUIRE (sem_wait (&started) == 0);
  delay = (struct timespec) {0, 50000000};
  REQUIRE (nanosleep (&delay, NULL) == 0);
  REQUIRE (__atomic_load_n (&worker_done, __ATOMIC_ACQUIRE) == 1);
  void *result = (void *) 99;
  REQUIRE (pthread_join (thread, &result) == 0 && result == NULL);
  REQUIRE (sem_destroy (&started) == 0);
  puts ("CLOCK_SLEEP_PASS blocked_wait_peer_progress complete");
  return 0;
}
