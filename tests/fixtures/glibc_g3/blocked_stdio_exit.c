/* SPDX-License-Identifier: Apache-2.0
   Expected: raw unsupported diagnostic and process exit status 127.
   The harness must enforce a timeout and check process resources recover. */
#define _GNU_SOURCE 1
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>

static atomic_int held;

static void *
hold_stdout (void *ignored)
{
  (void) ignored;
  flockfile (stdout);
  atomic_store_explicit (&held, 1, memory_order_release);
  for (;;)
    sched_yield ();
}

int
main (void)
{
  pthread_t worker;
  puts ("G3-T BEGIN active worker owns stdout");
  fflush (stdout);
  if (pthread_create (&worker, NULL, hold_stdout, NULL) != 0)
    return 1;
  while (!atomic_load_explicit (&held, memory_order_acquire))
    sched_yield ();
  /* No stdio call may be used after the worker owns stdout. */
  exit (0);
}
