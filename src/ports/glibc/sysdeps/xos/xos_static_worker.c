/* SPDX-License-Identifier: Apache-2.0 */
#include <tls.h>
#include <ldsodefs.h>
#include "xos_static_worker.h"
#include "xos_thread_entry.h"
#include "xos_thread_exit.h"
#include "xos_thread_tls.h"

struct worker_start
{
  struct xos_thread_entry_args trampoline;
  struct xos_thread_worker worker;
};

static void
run_worker (void *argument)
{
  const struct worker_start *state = argument;
  struct xos_thread_worker worker = state->worker;
  void *result = worker.run (worker.argument);
  worker.cleanup ();
  __xos_thread_finish ((unsigned long) result, worker.last_process_exit);
}

static xos_i64
setup_worker (const struct xos_thread_reservation *reservation,
              struct xos_thread_start_parameters *parameters, void *argument)
{
  /* The kernel provides a 16-byte-aligned top. Leave the startup record
     above RSP so the trampoline's call cannot overwrite it. */
  xos_u64 bytes = (sizeof (struct worker_start) + 15U) & -16UL;
  xos_u64 stack = reservation->stack_top - bytes;
  struct worker_start *state = (struct worker_start *) stack;
  struct pthread *pd;
#ifdef SHARED
  int error = __xos_thread_shared_tls_initialize (reservation, &pd);
#else
  int error = __xos_thread_static_tls_initialize (reservation, &pd);
#endif
  if (error != 0)
    return error == -1 ? -17 : -18;
#ifdef THREAD_COPY_STACK_GUARD
  THREAD_COPY_STACK_GUARD (pd);
#endif
#ifdef THREAD_COPY_POINTER_GUARD
  THREAD_COPY_POINTER_GUARD (pd);
#endif
  state->worker = *(const struct xos_thread_worker *) argument;
  if (state->worker.prepare != 0)
    {
      xos_i64 status = state->worker.prepare (pd, reservation,
                                             &state->worker.argument);
      if (status != 0)
        return status;
    }
  state->trampoline.run = run_worker;
  state->trampoline.argument = state;
  *parameters = (struct xos_thread_start_parameters) {
    .entry = (xos_u64) __xos_thread_entry, .argument = stack, .stack = stack,
    .thread_pointer = (xos_u64) TLS_TPADJ (pd)
  };
  return 0;
}

xos_i64
#ifdef SHARED
__xos_shared_worker_launch (xos_u64 stack_bytes, xos_u64 flags,
#else
__xos_static_worker_launch (xos_u64 stack_bytes, xos_u64 flags,
#endif
                            const struct xos_thread_worker *worker,
                            struct xos_thread_launch_result *result)
{
  /* Static TLS and TCB, worst-case TP/DTV alignment and reserved DTV slots.
     The kernel rounds the request to a page boundary. */
  const xos_u64 limit = 0x120000;
  xos_u64 tls = GLRO (dl_tls_static_size);
  xos_u64 alignment = GLRO (dl_tls_static_align);
#ifdef SHARED
  const xos_u64 dtv_slots = XOS_SHARED_DTV_SLOTS;
#else
  const xos_u64 dtv_slots = 3;
#endif
  xos_u64 dtv = dtv_slots * sizeof (dtv_t) + _Alignof (dtv_t) - 1;
  if (tls > limit || alignment == 0 || alignment > limit
      || tls + alignment - 1 + dtv > limit)
    {
      *result = (struct xos_thread_launch_result) { 0 };
      return -17;
    }
  /* All per-thread storage is inside the reservation, including the DTV,
     so abort itself releases the storage if start does not consume it. */
  return __xos_thread_launch (stack_bytes, tls + alignment - 1 + dtv, flags,
                              setup_worker, 0, (void *) worker, result);
}
