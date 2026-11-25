/* SPDX-License-Identifier: Apache-2.0 */
#include <unistd.h>
#include <limits.h>
#include "xos_console.h"
ssize_t
__read (int descriptor, void *buffer, size_t length)
{
  if (descriptor != 0)
    { __set_errno (EBADF); return -1; }
  if (length > LONG_MAX)
    { __set_errno (EINVAL); return -1; }
  return xos_console_transfer (0, descriptor, (uintptr_t) buffer, length);
}
libc_hidden_def (__read)
weak_alias (__read, read)
