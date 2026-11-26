/* SPDX-License-Identifier: Apache-2.0 */
#include <fcntl.h>
#include <unistd.h>

int
main (void)
{
  int fd = open ("/tests/input", O_RDONLY);
  int cleanup = open ("/tests/cleanup", O_RDWR);
  if (fd < 0 || cleanup < 0 || dup2 (fd, 10) != 10 || dup2 (fd, 11) != 11
      || dup2 (cleanup, 12) != 12 || close (fd) != 0 || close (cleanup) != 0
      || fcntl (12, F_SETFD, FD_CLOEXEC) != 0)
    return 72;
  char *const argv[] = { "d1_libc_handoff", "ordinary", 0 };
  execv ("/usr/bin/d1_libc_handoff", argv);
  return 73;
}
