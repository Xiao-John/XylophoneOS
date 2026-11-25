/* SPDX-License-Identifier: Apache-2.0 */
#include <unistd.h>
#include "xos_console.h"
int
__close (int descriptor)
{
  if (descriptor < 0 || descriptor > 2)
    { __set_errno (EBADF); return -1; }
  return (int) xos_console_call (13, descriptor, 0, 0);
}
libc_hidden_def (__close)
weak_alias (__close, close)
