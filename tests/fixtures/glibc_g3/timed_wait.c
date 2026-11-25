/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include "xos_timed_wait.h"

static xos_u32 word = 7;
static long clocks[8];
static unsigned clocks_used, clocks_size, waits;
static xos_u64 expected_deadline;
static xos_i64 wait_result;
static xos_u64 second_deadline;
static xos_i64 second_result;

long
__xos_clock_test_trap (unsigned long number, unsigned long first)
{
  assert (first == 0);
  assert (number == ((clocks_used & 1) ? 64UL : 46UL));
  assert (clocks_used < clocks_size);
  return clocks[clocks_used++];
}

xos_i64
__xos_wait_word (xos_u32 *address, xos_u32 expected, xos_u64 deadline)
{
  assert (address == &word && expected == 7);
  assert (deadline == (waits == 0 ? expected_deadline : second_deadline));
  ++waits;
  return waits == 1 ? wait_result : second_result;
}

xos_i64
__xos_wake_word (xos_u32 *address, xos_u32 count)
{
  (void) address; (void) count;
  assert (0);
  return 0;
}

static void
reset (xos_i64 result, xos_u64 deadline)
{
  clocks_used = clocks_size = waits = 0;
  wait_result = result;
  expected_deadline = deadline;
  second_deadline = 0;
  second_result = 0;
  errno = EDOM;
}

int
main (void)
{
  reset (0, 12000000345ULL);
  assert (__xos_wait_monotonic (&word, 7, 1, 12, 345) == 0);
  assert (waits == 1 && clocks_used == 0 && errno == EDOM);
  reset (-14, ~(xos_u64) 0);
  assert (__xos_wait_realtime (&word, 7, 0, 0, 0) == EAGAIN);
  assert (waits == 1 && clocks_used == 0 && errno == EDOM);
  reset (0, 0);
  assert (__xos_wait_monotonic (&word, 7, 1, -1, 0) == ETIMEDOUT);
  assert (__xos_wait_realtime (&word, 7, 1, -1, 0) == ETIMEDOUT);
  assert (__xos_wait_monotonic (&word, 7, 1, -1, -1) == EINVAL);
  assert (__xos_wait_realtime (&word, 7, 1, -1, -1) == EINVAL);
  assert (__xos_wait_realtime (&word, 7, 1, 1, 1000000000) == EINVAL);
  assert (__xos_wait_monotonic (&word, 7, 1, LLONG_MAX, 0) == EOVERFLOW);
  assert (__xos_wait_realtime (&word, 7, 1, LLONG_MAX, 0) == EOVERFLOW);
  assert (__xos_wait_monotonic (&word, 7, 1, 18446744073LL, 709551615) == EOVERFLOW);
  assert (__xos_wait_realtime (&word, 7, 1, 18446744073LL, 709551615) == EOVERFLOW);
  assert (!waits && !clocks_used);
  reset (0, 1100);
  clocks[0] = 100; clocks[1] = 1000; clocks_size = 2;
  assert (__xos_wait_realtime (&word, 7, 1, 0, 2000) == 0);
  assert (waits == 1 && clocks_used == 2 && errno == EDOM);
  reset (-14, 1100);
  clocks_size = 2;
  assert (__xos_wait_realtime (&word, 7, 1, 0, 2000) == EAGAIN);
  reset (-13, 300);
  clocks[0] = 100; clocks[1] = 1000;
  clocks[2] = 300; clocks[3] = 1200; clocks_size = 4;
  assert (__xos_wait_realtime (&word, 7, 1, 0, 1200) == ETIMEDOUT);
  assert (waits == 1 && clocks_used == 4);
  /* A delayed realtime read translates the first deadline too early.
     The adapter must continue waiting, and a later wake must succeed. */
  reset (-13, 300);
  clocks[0] = 100; clocks[1] = 1000;
  clocks[2] = 300; clocks[3] = 1100; clocks_size = 4;
  second_deadline = 400;
  assert (__xos_wait_realtime (&word, 7, 1, 0, 1200) == 0);
  assert (waits == 2 && clocks_used == 4);
  reset (0, 0);
  clocks[0] = 100; clocks[1] = 1200; clocks_size = 2;
  assert (__xos_wait_realtime (&word, 7, 1, 0, 1200) == ETIMEDOUT && waits == 0);
  reset (0, 0);
  clocks[0] = 100; clocks[1] = -5; clocks_size = 2;
  assert (__xos_wait_realtime (&word, 7, 1, 0, 1200) == EIO && waits == 0);
  reset (0, 0);
  clocks[0] = -1; clocks[1] = 1000; clocks_size = 2;
  assert (__xos_wait_realtime (&word, 7, 1, 0, 1200) == EOVERFLOW && waits == 0);
  reset (0, 0);
  clocks[0] = LLONG_MAX; clocks[1] = 0; clocks_size = 2;
  assert (__xos_wait_realtime (&word, 7, 1, 18446744073LL, 709551614) == EOVERFLOW);
  assert (waits == 0 && errno == EDOM);
  return 0;
}
