/* SPDX-License-Identifier: Apache-2.0
   Public declarations must work with the ordinary POSIX feature selection. */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <limits.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define REQUIRE(test) do { if (!(test)) { \
  printf ("TIMER_NONE_FAIL line=%d errno=%d\n", __LINE__, errno); exit (1); \
} } while (0)
static uint64_t ns (struct timespec value)
{
  return (uint64_t) value.tv_sec * 1000000000 + value.tv_nsec;
}
static void pause_ms (unsigned milliseconds)
{
#ifdef XOS_TIMER_NATIVE_SLEEP
  /* Explicit staging mode for a baseline SDK whose nanosleep is still a
     stub. This does not qualify public nanosleep; the default path does. */
  struct timespec start;
  REQUIRE (clock_gettime (CLOCK_MONOTONIC, &start) == 0);
  uint64_t deadline = ns (start) + (uint64_t) milliseconds * 1000000;
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
int main (int argc, char **argv)
{
  (void) argv;
  struct sigevent none = {.sigev_notify = SIGEV_NONE};
  struct itimerspec value, unchanged = {{12, 13}, {14, 15}};
  timer_t pool[32], extra = (timer_t) (uintptr_t) 73;
  for (unsigned i = 0; i < 32; ++i)
    REQUIRE (timer_create (i & 1 ? CLOCK_REALTIME : CLOCK_MONOTONIC,
                           &none, &pool[i]) == 0);
  REQUIRE (timer_create (CLOCK_MONOTONIC, &none, &extra) == -1
           && errno == EAGAIN && extra == (timer_t) (uintptr_t) 73);
  for (unsigned i = 0; i < 32; ++i)
    REQUIRE (timer_delete (pool[i]) == 0);
  REQUIRE (timer_create (CLOCK_MONOTONIC, &none, &extra) == 0 && extra != pool[0]);
  REQUIRE (timer_gettime (pool[0], &unchanged) == -1 && errno == EINVAL);
  REQUIRE (unchanged.it_interval.tv_sec == 12 && unchanged.it_value.tv_sec == 14);
  REQUIRE (timer_delete (pool[0]) == -1 && errno == EINVAL);
  REQUIRE (timer_getoverrun (pool[0]) == -1 && errno == EINVAL);
  puts ("TIMER_NONE_PASS pool_32_exhaustion_recovery_generation");

  struct itimerspec initial = {{0, 20000000}, {0, 20000000}};
  REQUIRE (timer_settime (extra, 0, &initial, NULL) == 0);
  pause_ms (75);
  REQUIRE (timer_gettime (extra, &value) == 0);
  REQUIRE (ns (value.it_interval) == 20000000 && ns (value.it_value) <= 20000000);
  REQUIRE (timer_getoverrun (extra) == 0); /* No asynchronous notification. */
  value = (struct itimerspec) {{0, 0}, {0, 10000000}};
  REQUIRE (timer_settime (extra, 0, &value, &value) == 0);
  REQUIRE (ns (value.it_interval) == 20000000); /* value == old is allowed. */
  pause_ms (25);
  REQUIRE (timer_gettime (extra, &value) == 0 && ns (value.it_value) == 0);
  puts ("TIMER_NONE_PASS periodic_phase_alias_old_one_shot");

  value = (struct itimerspec) {{0, 0}, {0, -1}};
  REQUIRE (timer_settime (extra, 0, &value, NULL) == -1 && errno == EINVAL);
  value.it_value = (struct timespec) {0, 1000000000};
  REQUIRE (timer_settime (extra, 0, &value, NULL) == -1 && errno == EINVAL);
  value.it_value = (struct timespec) {INT64_MAX, 0};
  REQUIRE (timer_settime (extra, 0, &value, NULL) == -1 && errno == EOVERFLOW);
  value.it_value = (struct timespec) {0, 0};
  REQUIRE (timer_settime (extra, 2, &value, NULL) == -1 && errno == EINVAL);
  REQUIRE (timer_settime (extra, 0, &value, NULL) == 0);
  struct sigevent unsupported = {.sigev_notify = SIGEV_SIGNAL};
  timer_t sentinel = (timer_t) (uintptr_t) 91;
  REQUIRE (timer_create (CLOCK_MONOTONIC, &unsupported, &sentinel) == -1
           && errno == ENOTSUP && sentinel == (timer_t) (uintptr_t) 91);
  REQUIRE (timer_create (CLOCK_MONOTONIC, NULL, &sentinel) == -1 && errno == ENOTSUP);
  REQUIRE (timer_create (CLOCK_PROCESS_CPUTIME_ID, &none, &sentinel) == -1
           && errno == ENOTSUP);
  REQUIRE (timer_create (CLOCK_THREAD_CPUTIME_ID, &none, &sentinel) == -1
           && errno == ENOTSUP);
  REQUIRE (timer_create ((clockid_t) 9876, &none, &sentinel) == -1 && errno == EINVAL);
  puts ("TIMER_NONE_PASS invalid_times_overflow_flags_unsupported");

  timer_t realtime;
  REQUIRE (timer_create (CLOCK_REALTIME, &none, &realtime) == 0);
  REQUIRE (clock_gettime (CLOCK_REALTIME, &value.it_value) == 0);
  value.it_interval = (struct timespec) {0, 0};
  REQUIRE (timer_settime (realtime, TIMER_ABSTIME, &value, NULL) == 0);
  REQUIRE (timer_gettime (realtime, &value) == 0 && ns (value.it_value) == 0);
  value.it_value = (struct timespec) {0, 20000000};
  REQUIRE (timer_settime (realtime, 0, &value, NULL) == 0);
  pause_ms (30);
  REQUIRE (timer_gettime (realtime, &value) == 0 && ns (value.it_value) == 0);
  REQUIRE (timer_delete (realtime) == 0);
  puts ("TIMER_NONE_PASS realtime_absolute_relative");

  if (argc > 1)
    {
      pid_t child = fork ();
      REQUIRE (child >= 0);
      if (child == 0)
        {
          REQUIRE (timer_gettime (extra, &value) == -1 && errno == EINVAL);
          timer_t created;
          REQUIRE (timer_create (CLOCK_MONOTONIC, &none, &created) == 0 && created != extra);
          REQUIRE (timer_delete (created) == 0);
          _exit (0);
        }
      int status;
      REQUIRE (waitpid (child, &status, 0) == child && WIFEXITED (status)
               && WEXITSTATUS (status) == 0);
      REQUIRE (timer_gettime (extra, &value) == 0);
      puts ("TIMER_NONE_PASS fork_child_reset_parent_preserved");
    }
  REQUIRE (timer_delete (extra) == 0);
  puts ("TIMER_NONE_PASS complete");
  return 0;
}
