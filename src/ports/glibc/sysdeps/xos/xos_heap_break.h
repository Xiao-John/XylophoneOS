/* SPDX-License-Identifier: Apache-2.0
   Native heap-break ABI shared by brk and the pre-TLS allocator.  */
#ifndef XOS_GLIBC_HEAP_BREAK_H
#define XOS_GLIBC_HEAP_BREAK_H 1

/* Match xos/process_abi.hpp.  The upper endpoint is a valid break.  */
#define XOS_HEAP_BEGIN 0x60000000UL
#define XOS_HEAP_END   0x70000000UL

static inline long int
xos_heap_break (unsigned long int requested)
{
#ifdef XOS_GLIBC_HEAP_TEST
  extern long int __xos_heap_test_trap (unsigned long int, unsigned long int);
  return __xos_heap_test_trap (29, requested);
#else
# if !defined __x86_64__ || defined __ILP32__
#  error "XOS heap support requires x86-64 LP64"
# endif
  long int result;
  __asm__ volatile ("int $0x80" : "=a" (result)
                    : "a" (29UL), "D" (requested), "S" (0UL), "d" (0UL)
                    : "memory", "cc");
  return result;
#endif
}

static inline int
xos_heap_break_in_range (unsigned long int address)
{
  return address >= XOS_HEAP_BEGIN && address <= XOS_HEAP_END;
}

#endif
