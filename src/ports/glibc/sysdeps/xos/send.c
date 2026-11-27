/* SPDX-License-Identifier: Apache-2.0 */
#include <sys/socket.h>
#include "xos_file_result.h"
#include "xos_net2_socket.h"

ssize_t
__send (int fd, const void *buffer, size_t length, int flags)
{
  if (flags & ~MSG_NOSIGNAL) return xos_file_result (-EOPNOTSUPP);
  return xos_file_result (__xos_net2_stream_fd (fd, (void *) buffer, length, 1));
}
libc_hidden_def (__send)
weak_alias (__send, send)
