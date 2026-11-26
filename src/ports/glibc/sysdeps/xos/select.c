/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <sys/select.h>
#include "xos_clock.h"
#include "xos_terminal_runtime.h"

/* XOS supports read readiness for one authenticated terminal descriptor.  */
int
__select (int nfds, fd_set *readfds, fd_set *writefds, fd_set *exceptfds,
          struct timeval *timeout)
{
  if (nfds < 0 || nfds > FD_SETSIZE
      || (timeout != NULL && (timeout->tv_sec < 0 || timeout->tv_usec < 0
                             || timeout->tv_usec >= 1000000)))
    {
      __set_errno (EINVAL);
      return -1;
    }

  int selected = -1;
  for (int fd = 0; fd < nfds; ++fd)
    {
      if ((writefds != NULL && FD_ISSET (fd, writefds))
          || (exceptfds != NULL && FD_ISSET (fd, exceptfds)))
        {
          __set_errno (ENOTSUP);
          return -1;
        }
      if (readfds != NULL && FD_ISSET (fd, readfds))
        {
          if (selected >= 0)
            {
              __set_errno (ENOTSUP);
              return -1;
            }
          selected = fd;
        }
    }
  if (selected < 0)
    {
      __set_errno (ENOTSUP);
      return -1;
    }

  const xos_u64 infinite = ~(xos_u64) 0;
  xos_u64 deadline = infinite;
  if (timeout != NULL)
    {
      long now = __xos_clock_trap (46, 0);
      if (now < 0)
        {
          __set_errno (EIO);
          return -1;
        }
      const xos_u64 room = infinite - 1 - (xos_u64) now;
      const xos_u64 fraction = (xos_u64) timeout->tv_usec * 1000;
      const xos_u64 seconds = (xos_u64) timeout->tv_sec;
      deadline = fraction > room || seconds > (room - fraction) / 1000000000
        ? infinite - 1 : (xos_u64) now + seconds * 1000000000 + fraction;
    }

  const long result = __xos_terminal_fd_readable (selected, deadline);
  if (result < 0 && result != -ETIMEDOUT)
    {
      __set_errno (-result);
      return -1;
    }

  FD_ZERO (readfds);
  if (writefds != NULL) FD_ZERO (writefds);
  if (exceptfds != NULL) FD_ZERO (exceptfds);
  if (result == 1) FD_SET (selected, readfds);
  return result == 1;
}
libc_hidden_def (__select)
weak_alias (__select, select)
