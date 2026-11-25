/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_GLIBC_THREAD_NAME_H
#define XOS_GLIBC_THREAD_NAME_H 1

#include "xos_thread_create.h"

enum { XOS_THREAD_NAME_SIZE = 16 };
struct xos_thread_attributes
{
  xos_u64 stack_bottom, stack_top, guard_size;
  int detached;
};
__attribute__ ((visibility ("hidden")))
int __xos_thread_name_add (xos_u64 tid);
__attribute__ ((visibility ("hidden")))
void __xos_thread_name_remove (xos_u64 tid);
__attribute__ ((visibility ("hidden")))
int __xos_thread_name_get (xos_u64 tid, char *output);
__attribute__ ((visibility ("hidden")))
int __xos_thread_name_set (xos_u64 tid, const char *name, unsigned long length);
/* A registered worker retains its entry until it begins native exit. */
__attribute__ ((visibility ("hidden")))
int __xos_thread_registered (xos_u64 tid);
__attribute__ ((visibility ("hidden")))
int __xos_thread_attributes_set (xos_u64 tid,
                                const struct xos_thread_attributes *attributes);
/* For the calling thread, native bounds initialize a lazy main-thread
   record. Other threads' metadata is copied while holding the registry
   lock. No reader retains a pointer into a reclaimable TCB. */
__attribute__ ((visibility ("hidden")))
int __xos_thread_attributes_get (xos_u64 tid, xos_u64 self_bottom,
                                xos_u64 self_top,
                                struct xos_thread_attributes *attributes);
__attribute__ ((visibility ("hidden")))
void __xos_thread_attributes_detach (xos_u64 tid);

#endif
