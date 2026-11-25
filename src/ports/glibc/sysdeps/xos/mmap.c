/* SPDX-License-Identifier: Apache-2.0 */
#include "xos_vm.h"

void *
__mmap (void *address, size_t length, int protection, int flags, int fd,
        off_t offset)
{
  uint64_t rounded = xos_vm_rounded_length (length);
  int error = xos_vm_protection_error (protection);
  if (rounded == 0)
    error = EINVAL;
  else if (error == 0
           && ((flags & ~(MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE))
               || (flags & (MAP_PRIVATE | MAP_ANONYMOUS))
                    != (MAP_PRIVATE | MAP_ANONYMOUS)
               || fd != -1 || offset != 0 || protection != PROT_NONE))
    error = ENOTSUP;
  if (error == 0)
    {
      /* Match the XOS reservation API.  mprotect commits pages when needed. */
      struct xos_vm_request request = {
        .version = 1, .size = sizeof (request), .operation = XOS_VM_RESERVE,
        .flags = (flags & MAP_FIXED_NOREPLACE) ? XOS_VM_EXACT : 0,
        .address = (uintptr_t) address, .length = rounded,
        .alignment = XOS_VM_PAGE
      };
      int64_t result = xos_vm_call (&request);
      if (result >= 0)
        return (void *) (uintptr_t) result;
      error = xos_vm_errno (result);
    }
  __set_errno (error);
  return MAP_FAILED;
}
weak_alias (__mmap, mmap)
libc_hidden_def (__mmap)
