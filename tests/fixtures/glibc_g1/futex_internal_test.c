/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <signal.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
#include <futex-internal.h>
#include "xos_timed_wait.h"

int __futex_abstimed_wait64 (unsigned *, unsigned, clockid_t, const struct __timespec64 *, int);
int __futex_abstimed_wait_cancelable64 (unsigned *, unsigned, clockid_t, const struct __timespec64 *, int);
int __futex_lock_pi64 (int *, clockid_t, const struct __timespec64 *, int);
static int next_result, seen, timed;
static xos_i64 sec;
static long ns;
int __xos_wait_monotonic (xos_u32 *word, xos_u32 expected, int has_deadline,
                          xos_i64 seconds, long nanoseconds)
{
  (void) word; (void) expected;
  ++seen; timed = has_deadline; sec = seconds; ns = nanoseconds;
  return next_result;
}
static int traps (int kind)
{
  pid_t pid = fork ();
  if (pid == 0)
    {
      unsigned word = 1;
      if (kind == 0) (void) __futex_abstimed_wait64 (&word, 1, CLOCK_MONOTONIC, 0, 128);
      if (kind == 1) (void) __futex_abstimed_wait_cancelable64 (&word, 1, CLOCK_MONOTONIC, 0, 0);
      if (kind == 2) { next_result = EFAULT; (void) __futex_abstimed_wait64 (&word, 1, CLOCK_MONOTONIC, 0, 0); }
      if (kind == 3) (void) __futex_lock_pi64 ((int *) &word, CLOCK_MONOTONIC, 0, 0);
      _exit (0);
    }
  int status;
  return pid > 0 && waitpid (pid, &status, 0) == pid && WIFSIGNALED (status) && (WTERMSIG (status) == SIGILL || WTERMSIG (status) == SIGTRAP);
}
int main (void)
{
  unsigned word = 1;
  struct __timespec64 deadline = { 12, 345 };
  next_result = EAGAIN;
  if (__futex_abstimed_wait64 (&word, 1, CLOCK_MONOTONIC, &deadline, 0) != EAGAIN ||
      seen != 1 || !timed || sec != 12 || ns != 345) return 1;
  next_result = 0;
  if (__futex_abstimed_wait64 (&word, 1, CLOCK_MONOTONIC, 0, 0) != 0 || timed || sec || ns) return 2;
  int before = seen;
  if (__futex_abstimed_wait64 (&word, 1, CLOCK_REALTIME, &deadline, 0) != EINVAL || seen != before) return 3;
  if (__futex_abstimed_wait64 (&word, 1, CLOCK_REALTIME, 0, 0) != 0 ||
      seen != before + 1 || timed || sec || ns) return 4;
  if (!traps (0) || !traps (1) || !traps (2) || !traps (3)) return 5;
  return 0;
}
