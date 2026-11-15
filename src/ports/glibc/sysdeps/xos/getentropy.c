/* SPDX-License-Identifier: Apache-2.0
   getentropy uses one atomic XOS random request of at most 256 bytes.  */
#include <errno.h>
#include <sys/random.h>

int
getentropy (void *buffer, size_t length)
{
  if (length > 256)
    { __set_errno (EIO); return -1; }
  ssize_t result = __getrandom (buffer, length, 0);
  if (result < 0)
    return -1;
  if ((size_t) result != length)
    { __set_errno (EIO); return -1; }
  return 0;
}
