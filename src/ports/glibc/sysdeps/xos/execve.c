/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <unistd.h>

extern int __xos_exec_path (const char *, char *const[], char *const[])
  __attribute__ ((visibility ("hidden")));
int
__execve (const char *path, char *const argv[], char *const envp[])
{
  const int error = __xos_exec_path (path, argv, envp);
  __set_errno (error);
  return -1;
}
weak_alias (__execve, execve)
