/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <sys/mman.h>
#include <shlib-compat.h>

int
__shm_open (const char *name, int flags, mode_t mode)
{
  (void) name;
  (void) flags;
  (void) mode;
  /* XOS has no POSIX shared-object namespace. */
  __set_errno (ENOSYS);
  return -1;
}
stub_warning (shm_open)
versioned_symbol (libc, __shm_open, shm_open, GLIBC_2_34);
