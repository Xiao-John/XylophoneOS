/* SPDX-License-Identifier: Apache-2.0 */
#include <limits.h>
#include <sys/uio.h>
#include <string.h>
#include "xos_file_result.h"
ssize_t __writev (int fd, const struct iovec *vectors, int count)
{
  if (count < 0 || count > 1024) return xos_file_result (-EINVAL);
  if (vectors == 0 && count != 0) return xos_file_result (-EFAULT);
  size_t requested = 0;
  for (int i = 0; i < count; ++i)
    {
      if (vectors[i].iov_len > (size_t) LONG_MAX - requested)
        return xos_file_result (-EINVAL);
      requested += vectors[i].iov_len;
    }
  /* One bounded write retains a single open description and one service
     request; split vectors must not interleave while advancing its offset. */
  unsigned char buffer[4096];
  size_t total = 0;
  for (int i = 0; i < count; ++i)
    {
      size_t length = vectors[i].iov_len;
      if (length > sizeof (buffer) - total) length = sizeof (buffer) - total;
      if (vectors[i].iov_base == 0 && length != 0) return xos_file_result (-EFAULT);
      if (length != 0) memcpy (buffer + total, vectors[i].iov_base, length);
      total += length;
      if (total == sizeof (buffer)) break;
    }
  return xos_file_result (__xos_file_write (fd, buffer, total));
}
libc_hidden_def (__writev)
weak_alias (__writev, writev)
