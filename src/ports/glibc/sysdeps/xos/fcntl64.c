/* SPDX-License-Identifier: Apache-2.0 */
#include <fcntl.h>
#include <stdarg.h>
#include "xos_file_result.h"
int __fcntl64 (int fd, int command, ...)
{
  int argument = 0;
  if (command == F_SETFD || command == F_SETFL || command == F_DUPFD
      || command == F_DUPFD_CLOEXEC)
    { va_list args; va_start (args, command); argument = va_arg (args, int); va_end (args); }
  return (int) xos_file_result (__xos_file_fcntl (fd, command, argument));
}
libc_hidden_def (__fcntl64)
weak_alias (__fcntl64, fcntl64)
