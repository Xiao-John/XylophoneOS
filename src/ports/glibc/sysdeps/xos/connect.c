/* SPDX-License-Identifier: Apache-2.0 */
#include <netinet/in.h>
#include <string.h>
#include "xos_file_result.h"
#include "xos_net2_socket.h"

int
__connect (int fd, __CONST_SOCKADDR_ARG peer, socklen_t length)
{
#ifdef __USE_GNU
  const struct sockaddr *address = peer.__sockaddr__;
#else
  const struct sockaddr *address = peer;
#endif
  struct sockaddr_in target;
  if (!address) return xos_file_result (-EFAULT);
  if (length < sizeof (target)) return xos_file_result (-EINVAL);
  memcpy (&target, address, sizeof (target));
  if (target.sin_family != AF_INET) return xos_file_result (-EAFNOSUPPORT);
  if (!target.sin_port) return xos_file_result (-EINVAL);
  return xos_file_result (__xos_net2_connect_fd (fd, ntohl (target.sin_addr.s_addr),
                                               ntohs (target.sin_port)));
}
weak_alias (__connect, connect)
libc_hidden_def (__connect)
