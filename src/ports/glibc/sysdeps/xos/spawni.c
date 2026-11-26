/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include "spawn_int.h"

extern int __xos_spawn_path (pid_t *, const char *, char *const [], char *const [])
  __attribute__ ((visibility ("hidden")));

int
__spawni (pid_t *pid, const char *path,
          const posix_spawn_file_actions_t *actions, const posix_spawnattr_t *attrs,
          char *const argv[], char *const envp[], int xflags)
{
  if (xflags != 0 || (actions != NULL && actions->__used != 0)
      || (attrs != NULL && attrs->__flags != 0))
    return ENOTSUP;
  return __xos_spawn_path (pid, path, argv, envp);
}
