/* SPDX-License-Identifier: Apache-2.0
   Fail explicitly until XOS supports reopening an existing file description. */
#include <stddef.h>
#include <errno.h>
#include <fd_to_filename.h>

char *
__fd_to_filename (int descriptor, struct fd_to_filename *storage)
{
  (void) descriptor;
  (void) storage;
  errno = ENOTSUP;
  return NULL;
}
