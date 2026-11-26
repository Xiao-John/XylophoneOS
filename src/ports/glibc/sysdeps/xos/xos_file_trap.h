/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_GLIBC_FILE_TRAP_H
#define XOS_GLIBC_FILE_TRAP_H 1
#include "xos_file_wire.h"

#ifdef XOS_GLIBC_FILE_TEST
extern long __xos_file_test_trap (xos_u64, xos_u64, xos_u64, xos_u64);
# define file_trap __xos_file_test_trap
#else
static inline long
file_trap (xos_u64 number, xos_u64 first, xos_u64 second, xos_u64 third)
{
  long result;
  __asm__ volatile ("int $0x80" : "=a" (result)
                    : "a" (number), "D" (first), "S" (second), "d" (third)
                    : "memory", "cc");
  return result;
}
#endif
#endif
