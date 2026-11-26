/* SPDX-License-Identifier: Apache-2.0 */
#include <stdio.h>
#include <string.h>
#include "xos_file_result.h"

int
rename (const char *old_path, const char *new_path)
{
  struct xos_file_request request = { 0 };
  struct xos_file_request destination = { 0 };
  struct xos_file_response response;
  long result = __xos_file_request_path (&request, old_path);
  if (result == 0) result = __xos_file_request_path (&destination, new_path);
  if (result == 0)
    {
      request.operation = 16;
      request.length = destination.name_length;
      _Static_assert (sizeof (request.data) >= sizeof (destination.name),
                      "rename destination field is too short");
      memcpy (request.data, destination.name, request.length);
      result = __xos_file_exchange (&request, &response);
    }
  return (int) xos_file_result (result);
}
