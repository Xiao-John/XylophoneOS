/* SPDX-License-Identifier: Apache-2.0 */
#include <sys/ioctl.h>
#include <stdarg.h>
#include <fcntl.h>
#include "xos_terminal_runtime.h"
#include "xos_file_result.h"

int
__ioctl (int fd, unsigned long command, ...)
{
  if (command == FIOCLEX || command == FIONCLEX)
    return (int) xos_file_result (__xos_file_fcntl (fd, F_SETFD,
                                  command == FIOCLEX ? FD_CLOEXEC : 0));
  if (command == TCGETS || command == TCSETS || command == TCSETSW || command == TCSETSF)
    {
      va_list arguments;
      va_start (arguments, command);
      struct termios *value = va_arg (arguments, struct termios *);
      va_end (arguments);
      long result = command == TCGETS ? __xos_terminal_tcgetattr (fd, value)
        : __xos_terminal_tcsetattr (fd, command == TCSETS ? TCSANOW
                                   : command == TCSETSW ? TCSADRAIN : TCSAFLUSH, value);
      return (int) xos_file_result (result);
    }
  /* Unknown and no-argument requests never consume an absent vararg. */
  struct xos_file_lease lease;
  long result = __xos_file_lease_acquire (fd, -1, &lease);
  if (result == 0)
    {
      (void) __xos_file_lease_release (&lease);
      result = -ENOTTY;
    }
  return (int) xos_file_result (result);
}
libc_hidden_def (__ioctl)
weak_alias (__ioctl, ioctl)
