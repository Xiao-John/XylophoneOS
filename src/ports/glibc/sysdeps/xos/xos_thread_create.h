/* SPDX-License-Identifier: Apache-2.0
   Private bridge to the XOS thread reservation protocol.  */
#ifndef XOS_GLIBC_THREAD_CREATE_H
#define XOS_GLIBC_THREAD_CREATE_H 1
#include "xos_wait_word.h"

struct xos_thread_header { xos_u32 version, size; xos_u64 reserved; };
struct xos_thread_prepare_request {
  struct xos_thread_header header;
  xos_u64 stack_bytes, tls_bytes, flags;
};
struct xos_thread_reservation {
  struct xos_thread_header header;
  xos_u64 tid, stack_bottom, stack_top, tls_begin, tls_end;
};
struct xos_thread_start_request {
  struct xos_thread_header header;
  xos_u64 tid, entry, argument, stack, thread_pointer;
};

struct xos_thread_start_parameters {
  xos_u64 entry, argument, stack, thread_pointer;
};
struct xos_thread_tls_layout {
  xos_u64 static_begin, thread_pointer, descriptor_end;
};
struct xos_thread_launch_result {
  xos_u64 tid; /* Access atomically if another thread observes it.  */
  xos_i64 abort_error;
  xos_u32 started;
};
typedef xos_i64 (*xos_thread_setup_fn) (const struct xos_thread_reservation *,
                                        struct xos_thread_start_parameters *,
                                        void *);
typedef void (*xos_thread_rollback_fn) (void *);

#ifdef __cplusplus
extern "C" {
#endif
/* Raw XOS results, not errno.  A successful prepare owns a reservation;
   start consumes it on success, otherwise the caller must abort it.  An
   abort failure requires the caller to resolve the reservation state.  These
   functions do not
   initialize TLS, publish a thread ID, or implement pthread_create.  */
__attribute__ ((visibility ("hidden")))
xos_i64 __xos_thread_prepare (xos_u64, xos_u64, xos_u64,
                              struct xos_thread_reservation *);
__attribute__ ((visibility ("hidden")))
xos_i64 __xos_thread_start (xos_u64, xos_u64, xos_u64, xos_u64, xos_u64);
__attribute__ ((visibility ("hidden")))
xos_i64 __xos_thread_abort (xos_u64);
/* Compute a TLS_TCB_AT_TP layout inside the reserved TLS range using the
   actual loader-provided static size/alignment and sizeof(struct pthread).
   Static TLS precedes TP, the descriptor starts at TP.  The static size
   includes the descriptor.  Does not initialize memory, DTV, or TLS.  On
   failure returns -1 and does not change the output.  */
__attribute__ ((visibility ("hidden")))
int __xos_thread_tls_layout (const struct xos_thread_reservation *,
                             xos_u64, xos_u64, xos_u64,
                             struct xos_thread_tls_layout *);
/* Setup runs while the reservation is owned by the caller and must fully
   initialize the TLS, entry and any data visible to the new thread before
   returning.  TID is published before start, but is tentative until launch
   returns.  An abort error leaves the ID available for caller recovery.
   On setup or start failure, rollback (if supplied) runs before abort while
   the reservation is still mapped; it must handle partial setup.  Setup and
   start errors are returned unchanged, separately from abort_error.
   Arguments must be valid; result must not own an earlier reservation and
   must not be modified concurrently.  */
__attribute__ ((visibility ("hidden")))
xos_i64 __xos_thread_launch (xos_u64, xos_u64, xos_u64,
                             xos_thread_setup_fn, xos_thread_rollback_fn, void *,
                             struct xos_thread_launch_result *);
#ifdef __cplusplus
}
#endif
#endif
