/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_GLIBC_STATIC_WORKER_H
#define XOS_GLIBC_STATIC_WORKER_H 1

#include "xos_thread_create.h"

struct xos_static_worker
{
  void *(*run) (void *);
  void *argument;
  void (*cleanup) (void);
  void (*last_process_exit) (void);
};

/* Requires an initialized static runtime and an enabled thread profile.
   RUN may return a native-width result. CLEANUP runs before the exit
   handshake. LAST_PROCESS_EXIT is required and must not return.
   The caller handles lifecycle state outside the reservation and must
   apply the rollback rules of __xos_thread_launch on failure. */
#ifndef SHARED
__attribute__ ((visibility ("hidden")))
xos_i64 __xos_static_worker_launch (xos_u64 stack_bytes, xos_u64 flags,
                                    const struct xos_static_worker *,
                                    struct xos_thread_launch_result *);
#endif
#endif
