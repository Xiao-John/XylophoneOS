/* SPDX-License-Identifier: Apache-2.0 */
#include <sched.h>
#include <threads.h>
void
thrd_yield (void)
{
  (void) __sched_yield ();
}
