/* SPDX-License-Identifier: Apache-2.0 */
#include "xos_vm.h"

int
__munmap (void *address, size_t length)
{
  return xos_vm_change (XOS_VM_UNMAP, address, length, PROT_NONE);
}
weak_alias (__munmap, munmap)
libc_hidden_def (__munmap)
