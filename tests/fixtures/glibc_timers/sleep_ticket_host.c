/* SPDX-License-Identifier: Apache-2.0 */
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "xos/sleep.h"
#include "xos_sleep.h"
#include "xos_thread_identity.h"

static unsigned long now_ns = 100, current_pid = 10, current_tid = 1;
static unsigned mode, calls, wake_fail;
static struct xos_sleep_ticket old_ticket, captured;

void __libc_fatal (const char *message)
{
  fputs (message, stderr);
  abort ();
}

long __xos_clock_test_trap (unsigned long number, unsigned long ignored)
{
  (void) ignored;
  assert (number == 46);
  return now_ns;
}
long __xos_thread_identity_test_call (unsigned long number, unsigned long address,
                                     unsigned long ignored)
{
  (void) ignored;
  assert (number == 41);
  struct xos_thread_info *info = (void *) address;
  memset (info, 0, sizeof (*info));
  info->pid = current_pid;
  info->tid = current_tid;
  return 0;
}
long __xos_wake_word (unsigned int *word, unsigned int count)
{
  assert (count == 1);
  return wake_fail && __atomic_load_n (word, __ATOMIC_ACQUIRE) ? -2 : 0;
}
long __xos_wait_word (unsigned int *word, unsigned int expected, unsigned long deadline)
{
  assert (expected == 0);
  ++calls;
  assert (xos_sleep_query (current_tid, &captured) == 0);
  assert (captured.pid == current_pid && captured.tid == current_tid);
  assert (captured.deadline_ns == deadline && captured.size == 48);
  if (mode == 1 || mode == 5)
    {
      assert (xos_sleep_interrupt (NULL) == EFAULT);
      struct xos_sleep_ticket malformed = captured;
      malformed.reserved2 = 1;
      assert (xos_sleep_interrupt (&malformed) == EINVAL);
      malformed = captured; ++malformed.pid;
      assert (xos_sleep_interrupt (&malformed) == EPERM);
      malformed = captured; ++malformed.sequence;
      assert (xos_sleep_interrupt (&malformed) == ESRCH);
      assert (xos_sleep_interrupt (&captured) == (mode == 5 ? EIO : 0));
      assert (xos_sleep_interrupt (&captured) == EALREADY);
      assert (__atomic_load_n (word, __ATOMIC_ACQUIRE) == 1);
      old_ticket = captured;
      now_ns += 20;
      return -14;
    }
  if (mode == 2)
    {
      assert (captured.sequence != old_ticket.sequence);
      assert (xos_sleep_interrupt (&old_ticket) == ESRCH);
      if (calls == 1) { now_ns += 10; return 0; }
      assert (calls == 2);
    }
  if (mode == 4)
    { now_ns = deadline; return -5; }
  if (mode == 6 && current_tid <= XOS_SLEEP_CAPACITY)
    {
      ++current_tid;
      unsigned long remaining = 99;
      int error = __xos_sleep_until (deadline, &remaining);
      assert (error == (current_tid == XOS_SLEEP_CAPACITY + 1 ? EAGAIN : 0));
      assert (remaining == 99);
      --current_tid;
    }
  now_ns = deadline;
  if (mode == 3)
    assert (xos_sleep_interrupt (&captured) == ETIMEDOUT);
  return -13;
}
int main (void)
{
  struct xos_sleep_ticket unchanged;
  memset (&unchanged, 0x55, sizeof (unchanged));
  struct xos_sleep_ticket original = unchanged;
  errno = EDOM;
  assert (xos_sleep_query (0, &unchanged) == EINVAL);
  assert (xos_sleep_query (1, NULL) == EFAULT);
  assert (xos_sleep_query (1, &unchanged) == ESRCH);
  assert (memcmp (&unchanged, &original, sizeof (original)) == 0);
  unsigned long remaining = 99;
  mode = 1;
  assert (__xos_sleep_until (1000, &remaining) == EINTR && remaining == 880);
  assert (xos_sleep_interrupt (&old_ticket) == ESRCH);
  assert (xos_sleep_query (1, &unchanged) == ESRCH);
  mode = 2; calls = 0; remaining = 99;
  assert (__xos_sleep_until (1000, &remaining) == 0 && remaining == 99);
  assert (calls == 2 && now_ns == 1000);
  mode = 3; calls = 0;
  assert (__xos_sleep_until (2000, &remaining) == 0 && remaining == 99);
  mode = 4;
  assert (__xos_sleep_until (3000, &remaining) == ENOMEM && remaining == 99);
  assert (xos_sleep_query (1, &unchanged) == ESRCH);
  mode = 5; wake_fail = 1; now_ns = 2000;
  assert (__xos_sleep_until (3000, &remaining) == EINTR && remaining == 980);
  wake_fail = 0;
  __xos_sleep_after_fork ();
  ++current_pid;
  assert (xos_sleep_interrupt (&old_ticket) == EPERM);
  mode = 6; remaining = 99; calls = 0;
  assert (__xos_sleep_until (4000, &remaining) == 0 && remaining == 99);
  assert (calls == XOS_SLEEP_CAPACITY);
  assert (xos_sleep_query (1, &unchanged) == ESRCH && errno == EDOM);
  puts ("SLEEP_TICKET_HOST_PASS cases=10 identity stale duplicate expired quota fork spurious native_error committed_wake_failure cleanup");
}
