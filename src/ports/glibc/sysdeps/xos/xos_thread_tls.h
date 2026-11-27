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
   before aborting the reservation.  Normal thread-exit reclamation is not yet
   implemented: the kernel can unmap TLS before a joiner can inspect it. */
__attribute__ ((visibility ("hidden")))
void __xos_thread_tls_release (struct pthread *);
#ifdef SHARED
# include "xos_rtld_pin_plan.h"
/* A fixed dependency plus the main image and interpreter can each own
   one TLS module. The GNU array also has length and generation entries. */
enum { XOS_SHARED_DTV_SLOTS = XOS_RTLD_MAX_PINS + 2 + 2 };
/* Both the TLS template and DTV stay in the native reservation until
   abort or kernel thread/process reaping. */
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
