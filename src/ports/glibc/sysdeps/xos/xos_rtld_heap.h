/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_RTLD_HEAP_H
#define XOS_RTLD_HEAP_H
#include <stddef.h>
#include "xos_rtld_heap_plan.h"

#define XOS_RTLD_HEAP_FAILED ((void *) (uintptr_t) -1)

#ifdef __cplusplus
extern "C" {
#endif

/* The native bootstrap already owns this empty reservation. Only the
   startup thread can allocate or seal it. Pages handed out remain live
   until process exit, including after GNU installs the regular allocator. */
int __xos_rtld_heap_begin (const struct xos_rtld_heap_plan *)
  __attribute__ ((visibility ("hidden")));
void *__xos_rtld_heap_grow (size_t) __attribute__ ((visibility ("hidden")));
int __xos_rtld_heap_seal (void) __attribute__ ((visibility ("hidden")));

#ifdef __cplusplus
}
#endif
#endif
