/* SPDX-License-Identifier: Apache-2.0 */
#include <rseq-internal.h>
int main (void)
{
  if (RSEQ_GETMEM_ONCE (cpu_id) >= 0) return 1;
  if (rseq_register_current_thread (0, false)) return 2;
  if (rseq_register_current_thread (0, true)) return 3;
  return 0;
}
