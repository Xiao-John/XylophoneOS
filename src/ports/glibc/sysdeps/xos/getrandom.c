/* SPDX-License-Identifier: Apache-2.0
   XOS random bytes; no Linux random-pool flag semantics are assumed.  */
#include <errno.h>
#include <sys/random.h>

ssize_t
__getrandom (void *buffer, size_t length, unsigned int flags)
{
  if (flags & ~(GRND_NONBLOCK | GRND_RANDOM | GRND_INSECURE))
    { __set_errno (EINVAL); return -1; }
  if (flags != 0)
    { __set_errno (ENOTSUP); return -1; }
  size_t count = length < 256 ? length : 256;
  long int result;
#ifdef XOS_GLIBC_RANDOM_TEST
  extern long int __xos_random_test_trap (void *, size_t);
  result = __xos_random_test_trap (buffer, count);
#else
# if !defined __x86_64__ || defined __ILP32__
#  error "XOS random bridge supports x86-64 LP64 only"
# endif
  __asm__ volatile ("int $0x80" : "=a" (result)
                    : "a" (63UL), "D" (buffer), "S" (count), "d" (0UL)
                    : "memory", "cc");
#endif
  if (result != 0)
    {
      __set_errno (result == -14 ? EFAULT : result == -22 ? EINVAL :
                   result == -38 ? ENOSYS : EIO);
      return -1;
    }
  return (ssize_t) count;
}
libc_hidden_def (__getrandom)
weak_alias (__getrandom, getrandom)
