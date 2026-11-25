/* SPDX-License-Identifier: Apache-2.0
   glibc program-break interface over XOS's native process heap.  */
#include <errno.h>
#include <unistd.h>
#include "xos_heap_break.h"

/* Used by glibc's generic sbrk.  Zero means its cache is not initialized.  */
void *__curbrk = NULL;

int
__brk (void *addr)
{
  unsigned long int requested = (unsigned long int) addr;
  long int result = xos_heap_break (requested);
  if (result < 0)
    {
      /* process_error_invalid, process_error_resources, thread_error_busy.
         A pinned page that prevents a shrink is distinct from exhaustion.  */
      switch (result)
        {
        case -2:
        case -5:
          __set_errno (ENOMEM);
          break;
        case -12:
          __set_errno (EBUSY);
          break;
        default:
          __set_errno (EIO);
        }
      return -1;
    }
  if (!xos_heap_break_in_range ((unsigned long int) result)
      || (requested != 0 && (unsigned long int) result != requested))
    {
      __set_errno (EIO);
      return -1;
    }
  __curbrk = (void *) (unsigned long int) result;
  return 0;
}
weak_alias (__brk, brk)
