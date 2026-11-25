/* SPDX-License-Identifier: Apache-2.0
   Expected: callback runs, stuck flush reaches kernel deadline, status 127.
   The harness must enforce a timeout and check process resources recover. */
#define _GNU_SOURCE 1
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

static atomic_int held;
static char buffer[512];
static pthread_mutex_t blocker_mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t blocker_cond = PTHREAD_COND_INITIALIZER;

static void
callback (void)
{
  const char message[] = "G3-X callback before blocked flush\n";
  if (write (2, message, sizeof (message) - 1) != sizeof (message) - 1)
    _exit (96);
}

static void *
hold_stdout (void *ignored)
{
  (void) ignored;
  flockfile (stdout);
  if (pthread_mutex_lock (&blocker_mutex) != 0)
    _exit (96);
  atomic_store_explicit (&held, 1, memory_order_release);
  /* Both application threads become blocked: deadline enforcement must also
     make progress when the scheduler is idle, without a spinning worker. */
  for (;;)
    if (pthread_cond_wait (&blocker_cond, &blocker_mutex) != 0)
      _exit (96);
}

int
main (void)
{
  pthread_t worker;
  if (setvbuf (stdout, buffer, _IOFBF, sizeof (buffer)) != 0)
    return 2;
  puts ("G3-T BEGIN active worker owns stdout");
  fflush (stdout);
  if (fputs ("G3-X pending bytes must not be reported flushed\n", stdout) < 0
      || atexit (callback) != 0)
    return 2;
  if (pthread_create (&worker, NULL, hold_stdout, NULL) != 0)
    return 1;
  while (!atomic_load_explicit (&held, memory_order_acquire))
    sched_yield ();
  /* No stdio call may be used after the worker owns stdout. */
  exit (0);
}
