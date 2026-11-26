/* SPDX-License-Identifier: Apache-2.0 */
#include <unistd.h>
#include "xos_file_result.h"

libc_hidden_proto (__isatty)

int __isatty (int fd)
{
  long result = __xos_file_isatty (fd);
  if (result < 0) { __set_errno ((int) -result); return 0; }
  return (int) result;
}
libc_hidden_def (__isatty)
weak_alias (__isatty, isatty)
