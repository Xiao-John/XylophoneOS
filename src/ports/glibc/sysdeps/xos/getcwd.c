/* SPDX-License-Identifier: Apache-2.0 */
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "xos_file_result.h"

char *
__getcwd (char *buffer, size_t size)
{
  if (buffer != NULL)
    {
      if (size == 0) { __set_errno (EINVAL); return NULL; }
      return xos_file_result (__xos_file_getcwd (buffer, size)) < 0 ? NULL : buffer;
    }
  char snapshot[sizeof (((struct xos_file_response *) 0)->name)];
  long length = xos_file_result (__xos_file_getcwd (snapshot, sizeof (snapshot)));
  if (length < 0) return NULL;
  if (size == 0) size = (size_t) length;
  if (size < (size_t) length) { __set_errno (ERANGE); return NULL; }
  buffer = malloc (size);
  if (buffer != NULL) memcpy (buffer, snapshot, (size_t) length);
  return buffer;
}
libc_hidden_def (__getcwd)
weak_alias (__getcwd, getcwd)
