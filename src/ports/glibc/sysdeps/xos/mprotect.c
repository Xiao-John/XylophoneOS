/* SPDX-License-Identifier: Apache-2.0 */
#include "xos_vm.h"

int
__mprotect (void *address, size_t length, int protection)
{
  return xos_vm_change (XOS_VM_PROTECT, address, length, protection);
}
weak_alias (__mprotect, mprotect)
libc_hidden_def (__mprotect)
