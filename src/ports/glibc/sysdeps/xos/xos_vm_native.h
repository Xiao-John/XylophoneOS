/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_GLIBC_VM_NATIVE_H
#define XOS_GLIBC_VM_NATIVE_H
#include <stdint.h>

#ifdef __cplusplus
# define XOS_VM_ASSERT static_assert
#else
# define XOS_VM_ASSERT _Static_assert
#endif
/* Wire layout from xos/vm_abi.hpp.  The port is independent of the C++
   SDK and uses the native trap rather than a Linux VM syscall.  */
struct xos_vm_request
{
  uint32_t version, size, operation, flags;
  uint64_t address, length, alignment;
  uint32_t protection, reserved0;
  uint64_t reserved1, reserved2;
};

XOS_VM_ASSERT (sizeof (struct xos_vm_request) == 64, "XOS VM ABI");
enum { XOS_VM_RESERVE = 1, XOS_VM_COMMIT = 2, XOS_VM_PROTECT = 3,
       XOS_VM_DECOMMIT = 4, XOS_VM_UNMAP = 5 };
enum { XOS_VM_RESOURCES = -4 };
enum { XOS_VM_PAGE = 4096, XOS_VM_EXACT = 1 };
#define XOS_VM_BEGIN UINT64_C (0x100000000000)
#define XOS_VM_END UINT64_C (0x200000000000)

#if !defined __x86_64__ || defined __ILP32__
# error "XOS VM support requires x86-64 LP64"
#endif

static inline int64_t
xos_vm_call (const struct xos_vm_request *request)
{
  int64_t result;
  __asm__ volatile ("int $0x80" : "=a" (result)
                    : "a" (67L), "D" (request), "S" (0L), "d" (0L)
                    : "memory", "cc");
  return result;
}

#undef XOS_VM_ASSERT
#endif
