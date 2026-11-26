/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include "xos_file_runtime.h"

extern xos_u32 d1_file_early_sequence;
extern long d1_file_early_failure;

int
main (void)
{
  char text[4];
  struct xos_file_request request = { .operation = 1 }; /* Ping the same files endpoint. */
  struct xos_file_response response;
  if (d1_file_early_failure != 0)
    {
      errno = 0;
      memset (&response, 0xff, sizeof (response));
      if (d1_file_early_sequence != 4 || read (0, text, sizeof (text)) != -1 || errno != EIO
          || __xos_file_exchange (&request, &response) != -EIO || response.request_id != 0)
        return 40;
      printf ("D1_FILE_DEATH early=%u error=%ld late=EIO\n",
              d1_file_early_sequence, d1_file_early_failure);
      return 0;
    }
  if (d1_file_early_sequence != 3 || read (0, text, sizeof (text)) != sizeof (text)
      || memcmp (text, "EFGH", sizeof (text)) != 0
      || __xos_file_exchange (&request, &response) != 0
      || response.request_id != d1_file_early_sequence + 2 || close (0) != 0)
    return 41;
  printf ("D1_FILE_HANDOFF early=%u late=%u inherited=EFGH\n",
          d1_file_early_sequence, response.request_id);
  return 0;
}
