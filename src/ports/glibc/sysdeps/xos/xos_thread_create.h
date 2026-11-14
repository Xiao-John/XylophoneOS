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

#ifdef __cplusplus
extern "C" {
#endif
/* Raw XOS results, not errno.  A successful prepare owns a reservation;
   start consumes it on success, otherwise the caller must abort it.  An
   abort failure leaves ownership with the caller.  These functions do not
   initialize TLS, publish a thread ID, or implement pthread_create.  */
__attribute__ ((visibility ("hidden")))
xos_i64 __xos_thread_prepare (xos_u64, xos_u64, xos_u64,
                              struct xos_thread_reservation *);
__attribute__ ((visibility ("hidden")))
xos_i64 __xos_thread_start (xos_u64, xos_u64, xos_u64, xos_u64, xos_u64);
__attribute__ ((visibility ("hidden")))
xos_i64 __xos_thread_abort (xos_u64);
#ifdef __cplusplus
}
#endif
#endif
