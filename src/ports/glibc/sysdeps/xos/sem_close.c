/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <semaphore.h>
#include <shlib-compat.h>

int
__sem_close (sem_t *semaphore)
{
  (void) semaphore;
  /* There are no valid named semaphore handles in this backend. */
  __set_errno (EINVAL);
  return -1;
}
versioned_symbol (libc, __sem_close, sem_close, GLIBC_2_34);
