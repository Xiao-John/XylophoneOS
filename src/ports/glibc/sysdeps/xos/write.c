/* SPDX-License-Identifier: Apache-2.0 */
#include <unistd.h>
#include <limits.h>
#include "xos_console.h"
ssize_t
__write (int descriptor, const void *buffer, size_t length)
{
  if (descriptor != 1 && descriptor != 2)
    { __set_errno (EBADF); return -1; }
  if (length > LONG_MAX)
    { __set_errno (EINVAL); return -1; }
  return xos_console_transfer (1, descriptor, (uintptr_t) buffer, length);
}
libc_hidden_def (__write)
weak_alias (__write, write)
