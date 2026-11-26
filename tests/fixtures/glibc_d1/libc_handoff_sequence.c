/* SPDX-License-Identifier: Apache-2.0 */
#include "xos_file_runtime.h"

long d1_handoff_sequence (void);

long
d1_handoff_sequence (void)
{
  struct xos_file_request request = { .operation = 1 }; /* Native files ping. */
  struct xos_file_response response;
  long result = __xos_file_exchange (&request, &response);
  return result == 0 ? (long) response.request_id : result;
}
