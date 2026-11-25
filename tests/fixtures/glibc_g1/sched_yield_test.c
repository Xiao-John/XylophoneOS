/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <errno.h>
static int calls;
void __xos_yield_test_trap (void) { ++calls; }
int __sched_yield (void);
int main (void)
{
  errno = 17;
  assert (__sched_yield () == 0 && calls == 1 && errno == 17);
  assert (__sched_yield () == 0 && calls == 2 && errno == 17);
}
