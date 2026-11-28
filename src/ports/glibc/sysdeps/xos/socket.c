/* SPDX-License-Identifier: Apache-2.0 */
#include <netinet/in.h>
#include <fcntl.h>
#include "xos_file_result.h"

int
__socket (int domain, int type, int protocol)
{
  if (domain != AF_INET) return xos_file_result (-EAFNOSUPPORT);
  if (protocol != 0 && protocol != IPPROTO_TCP) return xos_file_result (-EPROTONOSUPPORT);
  if ((type & ~(SOCK_CLOEXEC | SOCK_NONBLOCK)) != SOCK_STREAM) return xos_file_result (-EOPNOTSUPP);
  return xos_file_result (__xos_file_socket (((type & SOCK_CLOEXEC) ? O_CLOEXEC : 0)
                                              | ((type & SOCK_NONBLOCK) ? O_NONBLOCK : 0)));
}
libc_hidden_def (__socket)
weak_alias (__socket, socket)
