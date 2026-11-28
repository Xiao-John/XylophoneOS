/* SPDX-License-Identifier: Apache-2.0 */
#include <sys/socket.h>
#include "xos_file_result.h"
#include "xos_net2_socket.h"
int
__getsockopt (int fd, int level, int option, void *value, socklen_t *length)
{
  if (level != SOL_SOCKET || option != SO_ERROR) return xos_file_result (-ENOPROTOOPT);
  if (!value || !length) return xos_file_result (-EFAULT);
  if (*length < sizeof (int)) return xos_file_result (-EINVAL);
  int error = 0;
  long result = __xos_net2_error_fd (fd, &error);
  if (!result) { *(int *) value = error; *length = sizeof (int); }
  return xos_file_result (result);
}
libc_hidden_def (__getsockopt)
weak_alias (__getsockopt, getsockopt)
