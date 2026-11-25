/* SPDX-License-Identifier: Apache-2.0 */
#include "xos_file_positioned.h"
#include "xos_file_runtime.h"
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <string.h>

static long
positioned_io (int fd, void *buffer, size_t length, long offset, int writing)
{
  if (offset < 0) return -EINVAL;
  if ((unsigned long) offset > 0xfffffffeUL) return -EOVERFLOW;
  if (length > (size_t) LONG_MAX) return -EINVAL;
  if (buffer == NULL && length != 0) return -EFAULT;
  struct xos_file_lease lease;
  long result = __xos_file_lease_acquire (fd, writing, &lease);
  if (result < 0) return result;
  if (lease.kind != xos_file_kind_file)
    result = -ESPIPE;
  else if ((lease.flags & O_DIRECTORY) != 0)
    result = -EISDIR;
  else
    {
      struct xos_file_request request = { 0 };
      struct xos_file_response response;
      size_t maximum = writing ? sizeof (request.data) : sizeof (response.data);
      if (length > maximum) length = maximum;
      request.operation = writing ? 31 : 30;
      request.handle = lease.handle;
      request.offset = (xos_u64) offset;
      request.length = (xos_u32) length;
      if (writing && length != 0) memcpy (request.data, buffer, length);
      result = __xos_file_exchange (&request, &response);
      if (result == 0)
        {
          if (!writing && response.length != 0) memcpy (buffer, response.data, response.length);
          result = (long) response.value;
        }
    }
  (void) __xos_file_lease_release (&lease);
  return result;
}

long
__xos_file_pread (int fd, void *buffer, size_t length, long offset)
{ return positioned_io (fd, buffer, length, offset, 0); }

long
__xos_file_pwrite (int fd, const void *buffer, size_t length, long offset)
{ return positioned_io (fd, (void *) buffer, length, offset, 1); }
