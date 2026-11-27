/* SPDX-License-Identifier: Apache-2.0 */
#include <poll.h>
#include "xos_file_result.h"
#include "xos_net2_socket.h"

int
__poll (struct pollfd *descriptors, nfds_t count, int timeout)
{
  return xos_file_result (__xos_net2_poll (descriptors, count, timeout));
}
libc_hidden_def (__poll)
weak_alias (__poll, poll)
