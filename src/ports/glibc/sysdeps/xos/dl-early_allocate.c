/* SPDX-License-Identifier: Apache-2.0
   Allocate initial static TLS from the XOS heap.  */

#if BUILD_PIE_DEFAULT
# pragma GCC visibility push(hidden)
#endif
#include <ldsodefs.h>
#include <stddef.h>
#include "xos_heap_break.h"

extern void *__curbrk;

void *
_dl_early_allocate (size_t size)
{
  /* Static libc calls this before installing the thread pointer.  Use the
     native trap directly so an error needs no TLS-backed errno access.  */
  unsigned long int previous = (unsigned long int) xos_heap_break (0);
  if (!xos_heap_break_in_range (previous) || size > XOS_HEAP_END - previous)
    return NULL;
  if (size != 0)
    {
      unsigned long int requested = previous + size;
      if (xos_heap_break (requested) != (long int) requested)
        return NULL;
      __curbrk = (void *) requested;
    }
  return (void *) previous;
}
