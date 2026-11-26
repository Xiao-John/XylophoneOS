/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

int main (void)
{
  if (mkdir ("/mutation//", 0700) != 0 || chdir ("/mutation") != 0) return 1;
  if (mkdir ("nested/", 0755) != 0) return 2;
  errno = 0;
  if (mkdir ("nested", 0755) != -1 || errno != EEXIST) return 3;
  int fd = open ("nested/input", O_CREAT | O_EXCL | O_WRONLY, 0600);
  if (fd < 0 || write (fd, "path mutation", 13) != 13 || close (fd) != 0) return 4;
  errno = 0;
  if (rmdir ("nested/input/") != -1 || errno != ENOTDIR) return 5;
  errno = 0;
  if (rmdir ("nested/") != -1 || errno != ENOTEMPTY) return 6;
  if (rename ("nested/input", "output") != 0 || rmdir ("nested//") != 0) return 7;
  errno = 0;
  if (rename ("nested/input", "gone") != -1 || errno != ENOENT) return 8;
  fd = open ("output", O_RDONLY);
  char data[14] = { 0 };
  if (fd < 0 || read (fd, data, sizeof (data)) != 13 || close (fd) != 0
      || strcmp (data, "path mutation") != 0) return 9;
  if (unlink ("output") != 0 || chdir ("/") != 0 || rmdir ("/mutation") != 0) return 10;
  puts ("GLIBC_PATH_MUTATION_PASS");
  return 0;
}
