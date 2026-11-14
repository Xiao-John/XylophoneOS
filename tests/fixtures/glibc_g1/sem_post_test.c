/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <errno.h>
#include <string.h>
#include <semaphore.h>
#include <internaltypes.h>
#include <limits.h>
int __new_sem_post (sem_t *);
static unsigned int *expected_address;
static int wake_count;
void futex_wake (unsigned int *address, int count, int private)
{
  assert (address == expected_address && count == 1 && private == 0);
  ++wake_count;
}
int main (void)
{
  sem_t sem;
  struct new_sem *state = (struct new_sem *) &sem;
  memset (&sem, 0, sizeof sem);
  state->data = SEM_VALUE_MAX;
  errno = 0;
  assert (__new_sem_post (&sem) == -1 && errno == EOVERFLOW);
  assert (state->data == SEM_VALUE_MAX && wake_count == 0);
  state->data = SEM_VALUE_MAX - 1;
  errno = 7;
  assert (__new_sem_post (&sem) == 0 && state->data == SEM_VALUE_MAX && errno == 7);
  assert (wake_count == 0);
  state->data = (UINT64_C(1) << SEM_NWAITERS_SHIFT) | 3;
  expected_address = (unsigned int *) &state->data;
  assert (__new_sem_post (&sem) == 0);
  assert (state->data == ((UINT64_C(1) << SEM_NWAITERS_SHIFT) | 4) && wake_count == 1);
}
