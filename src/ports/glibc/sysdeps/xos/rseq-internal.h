/* SPDX-License-Identifier: Apache-2.0
   XOS does not implement the restartable-sequences kernel protocol.  */
#ifndef XOS_GLIBC_RSEQ_INTERNAL_H
#define XOS_GLIBC_RSEQ_INTERNAL_H 1
#include <stdbool.h>
struct pthread;
/* Only the cpu_id query used by generic NPTL is defined.  A negative value
   prevents an unregistered parent from claiming registration in its child. */
#define XOS_RSEQ_UNAVAILABLE_cpu_id (-2)
#define RSEQ_GETMEM_ONCE(member) XOS_RSEQ_UNAVAILABLE_##member
static inline bool
rseq_register_current_thread (struct pthread *self, bool requested)
{
  (void) self;
  (void) requested;
  /* The caller must not report rseq as registered or continue if it was
     required.  Public rseq ABI and TLS publication are not implemented. */
  return false;
}
#endif
