/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_GLIBC_VM_H
#define XOS_GLIBC_VM_H

#include <errno.h>
#include <stdint.h>
#include <sys/mman.h>

#include "xos_vm_native.h"

static inline int
xos_vm_errno (int64_t result)
{
  switch (result)
    {
    case -1: return EINVAL;
    case -2: return EFAULT;
    case -3: return EACCES;
    case -4:
    case -6: return ENOMEM;
    case -5:
    case -114: return EBUSY; /* VM pin or active IPC grant.  */
    case -7: return EEXIST;
    case -8: return ESRCH;
    default: return EIO;
    }
}

static inline uint64_t
xos_vm_rounded_length (size_t length)
{
  if (length == 0 || length > UINT64_MAX - (XOS_VM_PAGE - 1))
    return 0;
  return (length + XOS_VM_PAGE - 1) & -(uint64_t) XOS_VM_PAGE;
}

static inline int
xos_vm_protection_error (int protection)
{
  if (protection & ~(PROT_READ | PROT_WRITE | PROT_EXEC))
    return EINVAL;
  if ((protection & (PROT_WRITE | PROT_EXEC)) == (PROT_WRITE | PROT_EXEC))
    return EACCES;
  if (protection != PROT_NONE && (protection & PROT_READ) == 0)
    return ENOTSUP;
  return 0;
}

static inline int
xos_vm_change (uint32_t operation, void *address, size_t length, int protection)
{
  uint64_t start = (uintptr_t) address;
  uint64_t rounded = xos_vm_rounded_length (length);
  int error = xos_vm_protection_error (protection);
  if (start % XOS_VM_PAGE != 0 || rounded == 0)
    error = EINVAL;
  else if (start < XOS_VM_BEGIN || start >= XOS_VM_END
           || rounded > XOS_VM_END - start)
    error = ENOTSUP;
  if (error == 0)
    {
      struct xos_vm_request request = {
        .version = 1, .size = sizeof (request), .operation = operation,
        .address = start, .length = rounded, .protection = protection
      };
      int64_t result = xos_vm_call (&request);
      if (result == 0)
        return 0;
      error = xos_vm_errno (result);
    }
  __set_errno (error);
  return -1;
}
#endif
