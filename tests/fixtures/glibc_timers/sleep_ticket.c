/* SPDX-License-Identifier: Apache-2.0 */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <limits.h>
#include <pthread.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
#include <xos/sleep.h>

#define REQUIRE(test) do { if (!(test)) { \
  printf ("SLEEP_TICKET_FAIL line=%d errno=%d\n", __LINE__, errno); \
  fflush (stdout); exit (1); } } while (0)

struct thread_stats
{
  uint32_t version, size;
  uint64_t reserved;
  uint32_t processes, threads, reservations, waiting, results, free_pages;
  uint32_t user_pages, kernel_stack_pages;
};
_Static_assert (sizeof (struct thread_stats) == 48, "native thread stats v1");
_Static_assert (sizeof (struct xos_sleep_ticket) == 48, "sleep ticket v1");

static uint64_t now_ns (clockid_t clock)
{
  struct timespec value;
  REQUIRE (clock_gettime (clock, &value) == 0);
  return (uint64_t) value.tv_sec * 1000000000 + value.tv_nsec;
}
static struct timespec split_ns (uint64_t value)
{
  return (struct timespec) {value / 1000000000, value % 1000000000};
}
static unsigned waiting_threads (void)
{
  struct thread_stats stats = {0};
  long result;
  __asm__ volatile ("int $0x80" : "=a" (result)
                    : "a" (50UL), "D" (&stats), "S" (0UL), "d" (0UL)
                    : "memory", "cc");
  REQUIRE (result == 0 && stats.version == 1 && stats.size == 48);
  return stats.waiting;
}

struct worker_state
{
  unsigned mode, second_wait;
  int result, error, second_result, second_errno;
  struct timespec remainder, second_remainder;
  uint64_t elapsed, second_elapsed;
};
static void *sleep_worker (void *argument)
{
  struct worker_state *state = argument;
  clockid_t clock = state->mode >= 2 ? CLOCK_REALTIME : CLOCK_MONOTONIC;
  int absolute = state->mode & 1;
  struct timespec request = absolute
    ? split_ns (now_ns (clock) + 2000000000) : (struct timespec) {2, 0};
  state->remainder = (struct timespec) {91, 92};
  errno = EDOM;
  uint64_t before = now_ns (CLOCK_MONOTONIC);
  state->result = state->mode == 0
    ? nanosleep (&request, &state->remainder)
    : clock_nanosleep (clock, absolute ? TIMER_ABSTIME : 0,
                       &request, &state->remainder);
  state->error = errno;
  state->elapsed = now_ns (CLOCK_MONOTONIC) - before;
  if (state->second_wait)
    {
      request = (struct timespec) {0, 150000000};
      state->second_remainder = (struct timespec) {71, 72};
      errno = EDOM;
      before = now_ns (CLOCK_MONOTONIC);
      state->second_result = nanosleep (&request, &state->second_remainder);
      state->second_errno = errno;
      state->second_elapsed = now_ns (CLOCK_MONOTONIC) - before;
    }
  return NULL;
}

static struct xos_sleep_ticket observe_blocked (pthread_t target,
                                               uint64_t previous_sequence,
                                               unsigned waiting)
{
  const uint64_t limit = now_ns (CLOCK_MONOTONIC) + 1000000000;
  struct xos_sleep_ticket ticket;
  for (;;)
    {
      int result = xos_sleep_query (target, &ticket);
      REQUIRE (result == 0 || result == ESRCH);
      if (result == 0 && ticket.sequence != previous_sequence
          && waiting_threads () >= waiting)
        break;
      REQUIRE (now_ns (CLOCK_MONOTONIC) < limit);
      sched_yield ();
    }
  REQUIRE (ticket.version == 1 && ticket.size == sizeof (ticket)
           && ticket.reserved == 0 && ticket.reserved2 == 0
           && ticket.pid == (uint64_t) getpid () && ticket.tid == target);
  printf ("SLEEP_TICKET_PENDING tid=%lu sequence=%lu deadline=%lu waiting=%u\n",
          (unsigned long) ticket.tid, (unsigned long) ticket.sequence,
          (unsigned long) ticket.deadline_ns, waiting_threads ());
  return ticket;
}

static void check_worker (const struct worker_state *state)
{
  REQUIRE (state->result == (state->mode == 0 ? -1 : EINTR));
  REQUIRE (state->error == (state->mode == 0 ? EINTR : EDOM));
  REQUIRE (state->elapsed < 1500000000);
  if (state->mode & 1)
    REQUIRE (state->remainder.tv_sec == 91 && state->remainder.tv_nsec == 92);
  else
    {
      uint64_t remaining = (uint64_t) state->remainder.tv_sec * 1000000000
        + state->remainder.tv_nsec;
      REQUIRE (remaining > 0 && remaining <= 2000000000
               && state->remainder.tv_nsec < 1000000000);
    }
  if (state->second_wait)
    REQUIRE (state->second_result == 0 && state->second_errno == EDOM
             && state->second_elapsed >= 150000000
             && state->second_elapsed < 1000000000
             && state->second_remainder.tv_sec == 71
             && state->second_remainder.tv_nsec == 72);
}

static void run_interruption (unsigned mode)
{
  pthread_t target;
  struct worker_state state = {.mode = mode, .second_wait = 1};
  REQUIRE (pthread_create (&target, NULL, sleep_worker, &state) == 0);
  struct xos_sleep_ticket ticket = observe_blocked (target, 0, 1);
  REQUIRE (pthread_cancel (target) == ENOTSUP);
  errno = EDOM;
  struct xos_sleep_ticket invalid = ticket;
  invalid.pid += 1;
  REQUIRE (xos_sleep_interrupt (&invalid) == EPERM && errno == EDOM);
  invalid = ticket; invalid.reserved = 1;
  REQUIRE (xos_sleep_interrupt (&invalid) == EINVAL);
  invalid = ticket; ++invalid.sequence;
  REQUIRE (xos_sleep_interrupt (&invalid) == ESRCH);
  REQUIRE (xos_sleep_interrupt (&ticket) == 0 && errno == EDOM);
  int duplicate = xos_sleep_interrupt (&ticket);
  REQUIRE (duplicate == EALREADY || duplicate == ESRCH);
  struct xos_sleep_ticket next = observe_blocked (target, ticket.sequence, 1);
  REQUIRE (next.tid == ticket.tid && next.sequence != ticket.sequence);
  REQUIRE (xos_sleep_interrupt (&ticket) == ESRCH);
  void *result = (void *) 99;
  REQUIRE (pthread_join (target, &result) == 0 && result == NULL);
  check_worker (&state);
  struct xos_sleep_ticket output = ticket;
  REQUIRE (xos_sleep_query (target, &output) == ESRCH);
  REQUIRE (memcmp (&output, &ticket, sizeof (ticket)) == 0);
  REQUIRE (xos_sleep_interrupt (&next) == ESRCH);
  printf ("SLEEP_TICKET_PASS mode=%u interrupted_remaining_late_identity_cleanup\n", mode);
}

static void check_capacity (void)
{
  pthread_t targets[3];
  struct worker_state states[3] = {{0}, {0}, {0}};
  struct xos_sleep_ticket tickets[3];
  for (unsigned index = 0; index < 3; ++index)
    REQUIRE (pthread_create (&targets[index], NULL, sleep_worker, &states[index]) == 0);
  for (unsigned index = 0; index < 3; ++index)
    tickets[index] = observe_blocked (targets[index], 0, 3);
  /* Three active worker waits plus the main-thread wait occupy all four
     real slots. The main wait must succeed without over-admitting a thread. */
  struct timespec delay = {0, 30000000};
  REQUIRE (nanosleep (&delay, NULL) == 0);
  for (unsigned index = 0; index < 3; ++index)
    REQUIRE (xos_sleep_interrupt (&tickets[index]) == 0);
  for (unsigned index = 0; index < 3; ++index)
    {
      REQUIRE (pthread_join (targets[index], NULL) == 0);
      check_worker (&states[index]);
    }
  REQUIRE (waiting_threads () == 0);
  puts ("SLEEP_TICKET_PASS four_real_wait_slots_recovered");
}

int main (int argc, char **argv)
{
  if (argc > 1 && strcmp (argv[1], "exec_child") == 0)
    {
      REQUIRE (argc == 3 && getpid () == strtol (argv[2], NULL, 10));
      struct xos_sleep_ticket ticket;
      REQUIRE (xos_sleep_query (pthread_self (), &ticket) == ESRCH);
      struct timespec delay = {0, 20000000};
      REQUIRE (nanosleep (&delay, NULL) == 0);
      puts ("SLEEP_TICKET_PASS same_pid_exec_clean_runtime");
      return 0;
    }
  if (argc > 1 && strcmp (argv[1], "fork_exec") == 0)
    {
      pid_t parent = getpid (), child = fork ();
      REQUIRE (child >= 0);
      if (child == 0)
        {
          struct xos_sleep_ticket inherited = {
            .version = 1, .size = sizeof (inherited), .pid = parent,
            .tid = pthread_self (), .sequence = 1,
            .deadline_ns = now_ns (CLOCK_MONOTONIC) + 2000000000};
          REQUIRE (xos_sleep_interrupt (&inherited) == EPERM);
          REQUIRE (xos_sleep_query (pthread_self (), &inherited) == ESRCH);
          char *missing[] = {"/bin/absent_sleep_image", NULL};
          REQUIRE (execv (missing[0], missing) == -1 && errno == ENOENT);
          struct timespec delay = {0, 20000000};
          REQUIRE (nanosleep (&delay, NULL) == 0);
          char pid[32]; snprintf (pid, sizeof (pid), "%ld", (long) getpid ());
          char *replacement[] = {argv[0], "exec_child", pid, NULL};
          execv (replacement[0], replacement);
          REQUIRE (0);
        }
      int status;
      REQUIRE (waitpid (child, &status, 0) == child && WIFEXITED (status)
               && WEXITSTATUS (status) == 0);
      puts ("SLEEP_TICKET_PASS fork_pid_failed_exec_successful_exec");
      return 0;
    }
  struct xos_sleep_ticket output;
  REQUIRE (xos_sleep_query (pthread_self (), &output) == ESRCH);
  for (unsigned mode = 0; mode < 4; ++mode)
    run_interruption (mode);
  check_capacity ();
  puts ("SLEEP_TICKET_PASS complete");
  return 0;
}
