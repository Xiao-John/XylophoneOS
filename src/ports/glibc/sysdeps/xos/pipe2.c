/* SPDX-License-Identifier: Apache-2.0 */
#include <unistd.h>
#include "xos_file_result.h"

int
__pipe2 (int output[2], int flags)
{
  return (int) xos_file_result (__xos_file_pipe (output, flags));
}
weak_alias (__pipe2, pipe2)
