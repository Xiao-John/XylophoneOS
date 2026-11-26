/* SPDX-License-Identifier: Apache-2.0 */
#include "xos_file_result.h"

int
xos_open_anonymous (void)
{
  return (int) xos_file_result (__xos_file_open_anonymous ());
}

int
xos_seal_anonymous (int fd)
{
  return (int) xos_file_result (__xos_file_seal_anonymous (fd));
}
