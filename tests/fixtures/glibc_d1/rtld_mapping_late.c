/* SPDX-License-Identifier: Apache-2.0 */
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include "xos_file_runtime.h"

extern xos_u32 d1_dependency_sequence (void);

int
main (void)
{
  char data[4];
  struct xos_file_request request = { .operation = 1 };
  struct xos_file_response response;
  if (read (0, data, sizeof (data)) != sizeof (data) || memcmp (data, "EFGH", sizeof (data)) != 0
      || __xos_file_exchange (&request, &response) != 0
      || response.request_id != d1_dependency_sequence () + 2 || close (0) != 0)
    return 43;
  printf ("D1_RTLD_DEPENDENCY_MAPPED early=%u late=%u inherited=EFGH\n",
          d1_dependency_sequence (), response.request_id);
  return 0;
}
