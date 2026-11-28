/* SPDX-License-Identifier: Apache-2.0 */
#include <sys/socket.h>
#include "xos_file_result.h"
#include "xos_net2_socket.h"

int
__shutdown (int fd, int how)
{
  return xos_file_result (__xos_net2_shutdown_fd (fd, how));
}
libc_hidden_def (__shutdown)
weak_alias (__shutdown, shutdown)
