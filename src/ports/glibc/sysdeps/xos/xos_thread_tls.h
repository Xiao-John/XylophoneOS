/* SPDX-License-Identifier: Apache-2.0
   Private glibc TLS setup in an XOS-owned thread reservation. */
#ifndef XOS_GLIBC_THREAD_TLS_H
#define XOS_GLIBC_THREAD_TLS_H 1
#include "xos_thread_create.h"
struct pthread;
/* 0 on success, -1 for an unsuitable region, -2 for DTV allocation failure.
   Output is modified only on success.  The caller still owns the reserved
   region and must complete all other pthread initialization before start. */
__attribute__ ((visibility ("hidden")))
int __xos_thread_tls_initialize (const struct xos_thread_reservation *,
                                 struct pthread **);
/* Only for a successfully initialized TLS before start.  Invoke exactly once
   before aborting the reservation.  Never invoke it on a reaped worker's
   TCB: native reaping can unmap that memory before a joiner can inspect it. */
__attribute__ ((visibility ("hidden")))
void __xos_thread_tls_release (struct pthread *);
#if defined SHARED && defined XOS_ONLINE_CLOSURE
/* Native thread reaping can unmap the TCB before a joiner sees it.  Retire
   only the independent GNU heap DTV, then free it from a non-leaving thread.
   Four private slots match the native process thread capacity.  Each worker
   reserves one before launch; a full table is an explicit resource error. */
enum { XOS_WORKER_DTV_RETIRE_SLOTS = 4 };
__attribute__ ((visibility ("hidden")))
int __xos_thread_tls_reserve (void);
__attribute__ ((visibility ("hidden")))
void __xos_thread_tls_cancel (int);
/* RETIRE is allocation-free and syscall-free, for the 42 -> 43 exit gap. */
__attribute__ ((visibility ("hidden")))
void __xos_thread_tls_retire (int, void *);
__attribute__ ((visibility ("hidden")))
void __xos_thread_tls_drain (void);
#endif
#ifdef SHARED
# include "xos_rtld_pin_plan.h"
/* A fixed dependency plus the main image and interpreter can each own
   one TLS module. The GNU array also has length and generation entries. */
enum { XOS_SHARED_DTV_SLOTS = XOS_RTLD_MAX_PINS + 2 + 2 };
/* The default profile keeps both the TLS template and DTV in the native
   reservation.  The explicit online profile uses GNU's expandable heap DTV;
   its caller must apply the reservation/retirement protocol above. */
__attribute__ ((visibility ("hidden")))
int __xos_thread_shared_tls_initialize (const struct xos_thread_reservation *,
                                        struct pthread **);
#else
/* Uses the reservation for both the TCB and the initial static DTV.
   The kernel reclaims both together. Do not call the heap-backed release
   function for this layout. Invalid layout returns -1 and an unsupported
   TLS module set returns -2. */
__attribute__ ((visibility ("hidden")))
int __xos_thread_static_tls_initialize (const struct xos_thread_reservation *,
                                       struct pthread **);
#endif
#endif
