/* SPDX-License-Identifier: Apache-2.0
   Obtain the calling process ID without truncating XOS identifiers.  */
#include <errno.h>
#include <limits.h>
#include <unistd.h>

_Static_assert (sizeof (pid_t) == sizeof (int), "revisit XOS pid_t range");

pid_t
__getpid (void)
{
  long int value;
#ifdef XOS_GLIBC_GETPID_TEST
  extern long int __xos_getpid_test_trap (void);
  value = __xos_getpid_test_trap ();
#else
# if !defined __x86_64__ || defined __ILP32__
#  error "XOS getpid supports x86-64 LP64 only"
# endif
  __asm__ volatile ("int $0x80" : "=a" (value)
                    : "a" (6UL), "D" (0UL), "S" (0UL), "d" (0UL)
                    : "memory", "cc");
#endif
  /* The current candidate uses a signed 32-bit pid_t, whereas the XOS ABI
     permits positive identifiers through INT64_MAX.  Failing is preferable
     to aliasing another process; the final pid_t ABI is not yet decided. */
  if (value > INT_MAX)
    {
#if !defined SHARED || !IS_IN (rtld)
      __set_errno (EOVERFLOW);
#endif
      return (pid_t) -1;
    }
  if (value <= 0)
    {
#if !defined SHARED || !IS_IN (rtld)
      __set_errno (EIO);
#endif
      return (pid_t) -1;
    }
  return (pid_t) value;
}
libc_hidden_def (__getpid)
weak_alias (__getpid, getpid)
libc_hidden_weak (getpid)
