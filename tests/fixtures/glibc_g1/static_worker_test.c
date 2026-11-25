/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <setjmp.h>
#include <tls.h>
#include "xos_static_worker.h"
#include "xos_thread_entry.h"
#include "xos_thread_exit.h"
#include "xos_thread_tls.h"

size_t dl_tls_static_size = 600, dl_tls_static_align = 64;
static _Alignas (16) unsigned char stack[65536];
static struct pthread pd;
static struct xos_thread_start_parameters initial;
static int setup_error, started, calls;
static xos_i64 prepare_error;
static jmp_buf finished;

int
__xos_thread_static_tls_initialize (const struct xos_thread_reservation *r,
                                     struct pthread **out)
{
  assert (r->tls_begin == 0x70000000);
  if (setup_error)
    return setup_error;
  *out = &pd;
  return 0;
}

xos_i64
__xos_thread_launch (xos_u64 stack_bytes, xos_u64 tls, xos_u64 flags,
                     xos_thread_setup_fn setup, xos_thread_rollback_fn rollback,
                     void *worker, struct xos_thread_launch_result *result)
{
  assert (stack_bytes == sizeof (stack) && tls == 718 && flags == 1);
  assert (rollback == 0);
  struct xos_thread_reservation reservation = {
    .stack_top = (xos_u64) (stack + sizeof (stack)), .tls_begin = 0x70000000
  };
  xos_i64 error = setup (&reservation, &initial, worker);
  if (error)
    return error;
  assert (initial.entry == (xos_u64) __xos_thread_entry);
  assert (initial.argument == initial.stack && initial.stack % 16 == 0);
  assert (initial.stack < reservation.stack_top
          && initial.stack >= (xos_u64) stack);
  assert (initial.thread_pointer == (xos_u64) &pd);
  ++started;
  result->tid = 19;
  return 0;
}

void
__xos_thread_entry (const struct xos_thread_entry_args *args)
{
  args->run (args->argument);
  __builtin_trap ();
}

static void *
run (void *argument)
{
  assert (calls++ == 0 && argument == stack);
  return &pd;
}

static xos_i64
prepare (struct pthread *descriptor, const struct xos_thread_reservation *r,
         void **argument)
{
  assert (descriptor == &pd && r->tls_begin == 0x70000000);
  assert (*argument == &initial);
  *argument = stack;
  return prepare_error;
}

static void
cleanup (void)
{
  assert (calls++ == 1);
}

static void
last_exit (void)
{
  __builtin_trap ();
}

void
__xos_thread_finish (unsigned long result, void (*last_process_exit) (void))
{
  assert (calls++ == 2 && result == (unsigned long) &pd);
  assert (last_process_exit == last_exit);
  longjmp (finished, 1);
}

int
main (void)
{
  struct xos_static_worker worker = {
    .run = run, .argument = &initial, .cleanup = cleanup,
    .last_process_exit = last_exit, .prepare = prepare
  };
  struct xos_thread_launch_result result;
  setup_error = -2;
  assert (__xos_static_worker_launch (sizeof (stack), 1, &worker, &result) == -18);
  assert (!started);
  setup_error = 0;
  prepare_error = -5;
  assert (__xos_static_worker_launch (sizeof (stack), 1, &worker, &result) == -5);
  assert (!started);
  prepare_error = 0;
  assert (__xos_static_worker_launch (sizeof (stack), 1, &worker, &result) == 0);
  assert (started == 1 && result.tid == 19);
  worker = (struct xos_static_worker) { 0 };
  if (setjmp (finished) == 0)
    __xos_thread_entry ((void *) initial.argument);
  assert (calls == 3);
}
