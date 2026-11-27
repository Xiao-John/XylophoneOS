/* SPDX-License-Identifier: Apache-2.0 */
#include <sys/socket.h>
#include "xos_file_result.h"
#include "xos_net2_socket.h"

ssize_t
__recv (int fd, void *buffer, size_t length, int flags)
{
  if (flags) return xos_file_result (-EOPNOTSUPP);
  return xos_file_result (__xos_net2_stream_fd (fd, buffer, length, 0));
}
libc_hidden_def (__recv)
weak_alias (__recv, recv)
