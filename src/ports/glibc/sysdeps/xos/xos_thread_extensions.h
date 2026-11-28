/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_GLIBC_THREAD_EXTENSIONS_H
#define XOS_GLIBC_THREAD_EXTENSIONS_H 1
#include <errno.h>
#include <limits.h>

struct xos_thread_cpu_sample
{
  unsigned int version, size;
  unsigned long reserved;
  unsigned long tid, user_ns, system_ns, elapsed_ns, resolution_ns;
};
struct xos_join_options
{
  unsigned int version, size;
  unsigned long reserved, deadline_ns, mode;
};
_Static_assert (sizeof (struct xos_thread_cpu_sample) == 56,
                "XOS target-thread CPU v1");
_Static_assert (sizeof (struct xos_join_options) == 32, "XOS join options v1");

static inline long
xos_thread_extension_call (unsigned long number, unsigned long first,
                           unsigned long second, unsigned long third)
{
#ifdef XOS_GLIBC_THREAD_EXTENSIONS_TEST
  extern long __xos_thread_extensions_test_call (unsigned long, unsigned long,
                                                unsigned long, unsigned long);
  return __xos_thread_extensions_test_call (number, first, second, third);
#else
  long result;
  __asm__ volatile ("int $0x80" : "=a" (result)
                    : "a" (number), "D" (first), "S" (second), "d" (third)
                    : "memory", "cc");
  return result;
#endif
}

static inline int
xos_thread_cpu_query (unsigned long tid, struct xos_thread_cpu_sample *sample)
{
  *sample = (struct xos_thread_cpu_sample)
    { .version = 1, .size = sizeof (*sample), .tid = tid };
  long result = xos_thread_extension_call (41, (unsigned long) sample, 1, 0);
  switch (result)
    {
    case 0: return 0;
    case -15: return ESRCH;
    case -11: return EFAULT;
    /* An older kernel rejects this explicit mode; it cannot substitute the
       calling thread's v1 info or CPU sample. */
    case -2: case -18: case -19: return ENOTSUP;
    default: return EIO;
    }
}

/* XOS has no other negative clock family. The private process-local encoding
   is -(TID+1), never a truncated TID. Native TIDs are never reused. */
static inline int
xos_thread_clock_encode (unsigned long tid, int *clock)
{
  if (tid == 0) return ESRCH;
  if (tid > (unsigned long) INT_MAX - 1) return EOVERFLOW;
  *clock = -(int) tid - 1;
  return 0;
}
static inline unsigned long
xos_thread_clock_decode (int clock)
{
  return (unsigned long) (-(long) clock - 1);
}
#endif
