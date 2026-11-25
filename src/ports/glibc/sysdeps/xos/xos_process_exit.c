/* SPDX-License-Identifier: Apache-2.0
   Bounded process cleanup with live peers, on the native XOS exit protocol. */
#include <unistd.h>
#include "xos_process_exit.h"

static long
exit_trap (unsigned long number, unsigned long first, unsigned long second)
{
  long result;
  __asm__ volatile ("int $0x80" : "=a" (result)
                    : "a" (number), "D" (first), "S" (second), "d" (0UL)
                    : "memory", "cc");
  return result;
}

void
__xos_process_exit_begin (void)
{
  const unsigned long budget = 30000000000UL;
  long now = exit_trap (46, 0, 0);
  if (now >= 0 && (unsigned long) now < ~0UL - budget)
    {
      struct xos_process_exit_cleanup_request request = {
        1, sizeof (request), 0, (unsigned long) now + budget, 127, 0
      };
      long result = exit_trap (51, 1, (unsigned long) &request);
      if (result == 0)
        return;
      if (result == -12)
        {
          /* Never acquire a libc lock while another exit owner is running
             callbacks. The kernel preserves its first deadline and status. */
          while (exit_trap (47, request.deadline_ns, 0) == 0)
            ;
        }
    }
  static const char message[] = "XOS glibc: process cleanup window failed\n";
  (void) exit_trap (1, (unsigned long) message, sizeof (message) - 1);
  _exit (127);
}
