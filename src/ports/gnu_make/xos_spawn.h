/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_GNU_MAKE_SPAWN_H
#define XOS_GNU_MAKE_SPAWN_H

#include <errno.h>
#include <fcntl.h>
#include <spawn.h>
#include <stdio.h>
#include <unistd.h>

/* GNU Make starts recipes from one thread. The XOS spawn implementation
   snapshots the parent's standard descriptors and transfers them to the child.
   Save both the source and original descriptors before changing their slots,
   since a source may itself be one of the standard descriptors. */
static int
xos_spawn_recipe (pid_t *pid, const char *path, char *const argv[],
                  char *const envp[], int fdin, int fdout, int fderr)
{
  const int targets[] = { FD_STDIN, FD_STDOUT, FD_STDERR };
  const int sources[] = { fdin >= 0 ? fdin : FD_STDIN, fdout, fderr };
  int originals[] = { -1, -1, -1 };
  int copies[] = { -1, -1, -1 };
  int original_flags[] = { -1, -1, -1 };
  int changed[] = { 0, 0, 0 };
  int result = 0;
  int restore_error = 0;
  int i;

  if (sources[0] != targets[0] || sources[1] != targets[1]
      || sources[2] != targets[2])
    if (fflush (NULL) == EOF)
      return errno;

  for (i = 0; i < 3; ++i)
    if (sources[i] != targets[i])
      {
        copies[i] = fcntl (sources[i], F_DUPFD_CLOEXEC, 3);
        if (copies[i] < 0)
          { result = errno; goto cleanup; }
        original_flags[i] = fcntl (targets[i], F_GETFD);
        if (original_flags[i] >= 0)
          {
            originals[i] = fcntl (targets[i], F_DUPFD_CLOEXEC, 3);
            if (originals[i] < 0)
              { result = errno; goto cleanup; }
          }
        else if (errno != EBADF)
          { result = errno; goto cleanup; }
      }

  for (i = 0; i < 3; ++i)
    if (copies[i] >= 0)
      {
        if (dup2 (copies[i], targets[i]) < 0)
          { result = errno; goto cleanup; }
        changed[i] = 1;
      }

  do
    result = posix_spawn (pid, path, NULL, NULL, argv, envp);
  while (result == EINTR);

 cleanup:
  for (i = 0; i < 3; ++i)
    {
      if (changed[i])
        {
          if (originals[i] < 0)
            restore_error |= close (targets[i]) < 0;
          else if (dup2 (originals[i], targets[i]) < 0
                   || fcntl (targets[i], F_SETFD, original_flags[i]) < 0)
            restore_error = 1;
        }
      if (originals[i] >= 0)
        close (originals[i]);
      if (copies[i] >= 0)
        close (copies[i]);
    }
  if (restore_error)
    O (fatal, NILF, _("cannot restore the standard descriptors after spawning"));
  return result;
}

#endif
