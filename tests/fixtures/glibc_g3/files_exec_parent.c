/* SPDX-License-Identifier: Apache-2.0
   Build with the existing newlib SDK. It exercises real replacement from a
   previously supported libc into the separately linked G3 glibc receiver. */
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

extern char **environ;
#define CHECK(condition) do { if (!(condition)) { \
  fprintf (stderr, "GLIBC_G3_FILES_PARENT_FAIL line=%d errno=%d\n", __LINE__, errno); \
  exit (1); } } while (0)

int main (int argc, char **argv)
{
  const char *child = argc > 1 ? argv[1] : "/bin/glibc-g3-files.elf";
  int original = open ("/glibc_g3_inherit.tmp", O_CREAT | O_EXCL | O_RDWR, 0644);
  CHECK (original >= 3);
  CHECK (write (original, "0123456789", 10) == 10);
  CHECK (lseek (original, 2, SEEK_SET) == 2);
  int alias = dup (original), clo_alias = dup (original);
  CHECK (alias >= 3 && clo_alias >= 3);
  CHECK (fcntl (clo_alias, F_SETFD, FD_CLOEXEC) == 0);
  int clo_only = open ("/glibc_g3_cloexec.tmp", O_CREAT | O_EXCL | O_RDWR, 0644);
  CHECK (clo_only >= 3 && fcntl (clo_only, F_SETFD, FD_CLOEXEC) == 0);
  CHECK (write (clo_only, "discard", 7) == 7);
  CHECK (dup2 (original, 31) == 31);
  char numbers[5][12];
  const int values[5] = { original, alias, clo_alias, clo_only, 31 };
  for (int i = 0; i < 5; ++i) snprintf (numbers[i], sizeof (numbers[i]), "%d", values[i]);
  char *arguments[] = { "glibc-g3-files", "inherit", numbers[0], numbers[1],
                        numbers[2], numbers[3], numbers[4], 0 };
  printf ("GLIBC_G3_FILES_PARENT_READY original=%d alias=%d clo_alias=%d clo_only=%d high=31\n",
          original, alias, clo_alias, clo_only);
  CHECK (fflush (stdout) == 0);
  execve (child, arguments, environ);
  CHECK (0);
  return 1;
}
