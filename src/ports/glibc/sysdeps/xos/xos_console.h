/* SPDX-License-Identifier: Apache-2.0
   G2 uses the inherited kernel standard handles.  G3 supplies the full
   userspace descriptor/file-service backend independently. */
#ifndef XOS_GLIBC_CONSOLE_H
#define XOS_GLIBC_CONSOLE_H 1
#include <errno.h>
#include <limits.h>
#include <stdint.h>
static inline long
xos_console_raw (unsigned long operation, unsigned long descriptor,
                 unsigned long buffer, unsigned long length)
{
  long result;
  __asm__ volatile ("int $0x80" : "=a" (result)
                    : "a" (operation), "D" (descriptor), "S" (buffer),
                      "d" (length) : "memory", "cc");
  return result;
}

static inline long
xos_console_result (long result)
{
  if (result < 0)
    {
      __set_errno (result == -1 ? EBADF : result == -2 ? EINVAL
                   : result == -3 ? EAGAIN : result == -7 ? EPIPE
                   : result == -11 ? EFAULT : EIO);
      return -1;
    }
  return result;
}

static inline long
xos_console_call (unsigned long operation, unsigned long descriptor,
                  unsigned long buffer, unsigned long length)
{
  return xos_console_result (xos_console_raw (operation, descriptor, buffer, length));
}

static inline long
xos_console_transfer (int writing, unsigned int descriptor,
                      uintptr_t buffer, unsigned long length)
{
  const int console = xos_console_raw (34, 0, descriptor, 0) == 1;
  if (writing && console && length > 256)
    length = 256;
  const int atomic_write = writing && !console && length <= 4096;
  const unsigned long handle = descriptor | (atomic_write ? 1UL << 63 : 0);
  for (;;)
    {
      long result = xos_console_raw (writing ? 11 : 12, handle, buffer, length);
      if (result >= 0)
        {
          if ((unsigned long) result > length)
            { __set_errno (EIO); return -1; }
          return result;
        }
      if (result != -3)
        return xos_console_result (result);
      /* G2 inherited standard handles are blocking.  Pipes have a native
         event wait; debug-serial input uses a bounded-rate timer wait. */
      if (!console)
        {
          result = xos_console_raw (54, descriptor,
                                    atomic_write ? length : writing ? 1 : 0, 0);
          if (result < 0)
            return xos_console_result (result);
        }
      else
        {
          long now = xos_console_raw (46, 0, 0, 0);
          if (now < 0 || now > LONG_MAX - 1000000
              || xos_console_raw (47, (unsigned long) now + 1000000, 0, 0) != 0)
            { __set_errno (EIO); return -1; }
        }
    }
}
#endif
