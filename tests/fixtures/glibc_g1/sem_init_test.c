/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <errno.h>
#include <string.h>
#include <semaphore.h>
#include <semaphoreP.h>
int __new_sem_init (sem_t *, int, unsigned int);
int main (void)
{
  sem_t sem, original;
  memset (&sem, 0xa5, sizeof sem);
  original = sem;
  errno = 0;
  assert (__new_sem_init (&sem, 1, 1) == -1 && errno == ENOTSUP);
  assert (memcmp (&sem, &original, sizeof sem) == 0);
  errno = 0;
  assert (__new_sem_init (&sem, -1, 1) == -1 && errno == ENOTSUP);
  assert (memcmp (&sem, &original, sizeof sem) == 0);
  errno = 0;
  assert (__new_sem_init (&sem, 0, (unsigned int) SEM_VALUE_MAX + 1u) == -1 && errno == EINVAL);
  assert (memcmp (&sem, &original, sizeof sem) == 0);
  errno = 7;
  assert (__new_sem_init (&sem, 0, SEM_VALUE_MAX) == 0 && errno == 7);
  struct new_sem state;
  memcpy (&state, &sem, sizeof state);
  assert (state.data == SEM_VALUE_MAX && state.private == FUTEX_PRIVATE);
}
