/* SPDX-License-Identifier: Apache-2.0
   Existing native runtime prepares a real shared description and directory
   objects, then forks/execs the isolated glibc public-API receiver. */
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

static pid_t active_child = -1;
#define CHECK(condition) do { if (!(condition)) { \
  fprintf (stderr, "GLIBC_FILES_EXTRA_PARENT_FAIL line=%d errno=%d\n", __LINE__, errno); \
  exit (1); } } while (0)

int main (int argc, char **argv)
{
  CHECK (argc == 2);
  CHECK (mkdir ("/g3_held", 0755) == 0 && mkdir ("/g3_detached", 0755) == 0);
  int file = open ("/g3_held/original", O_CREAT | O_EXCL | O_RDWR, 0644);
  CHECK (file >= 3 && close (file) == 0);
  int held = open ("/g3_held", O_RDONLY | O_DIRECTORY);
  int detached = open ("/g3_detached", O_RDONLY | O_DIRECTORY);
  file = open ("/g3_shared", O_CREAT | O_EXCL | O_RDWR, 0644);
  CHECK (held >= 3 && detached >= 3 && file >= 3);
  unsigned char pattern[512];
  for (unsigned int i = 0; i < sizeof (pattern); ++i) pattern[i] = (unsigned char) (i & 255);
  CHECK (write (file, pattern, sizeof (pattern)) == sizeof (pattern) && lseek (file, 0, SEEK_SET) == 0);
  int ready[2], go[2];
  CHECK (pipe (ready) == 0 && pipe (go) == 0);
  /* Assign snapshots after all low-numbered descriptors have been allocated. */
  CHECK (dup2 (file, 10) == 10 && dup2 (held, 12) == 12 && dup2 (detached, 14) == 14);
  CHECK (close (file) == 0 && close (held) == 0 && close (detached) == 0);
  fflush (stdout);
  active_child = fork ();
  CHECK (active_child >= 0);
  if (active_child == 0) {
    CHECK (close (ready[0]) == 0 && close (go[1]) == 0);
    CHECK (dup2 (ready[1], 11) == 11 && dup2 (go[0], 13) == 13);
    CHECK (close (ready[1]) == 0 && close (go[0]) == 0);
    char *arguments[] = { "g3_files_extra_receiver", "inherited", NULL };
    execv (argv[1], arguments);
    _exit (71);
  }
  CHECK (close (ready[1]) == 0 && close (go[0]) == 0);
  CHECK (close (12) == 0 && close (14) == 0);
  char byte;
  CHECK (read (ready[0], &byte, 1) == 1 && byte == 'R');
  CHECK (rename ("/g3_held", "/g3_moved") == 0 && mkdir ("/g3_held", 0755) == 0);
  CHECK (rmdir ("/g3_detached") == 0 && mkdir ("/g3_detached", 0755) == 0);
  CHECK (write (go[1], "G", 1) == 1);
  for (unsigned int i = 0; i < sizeof (pattern); ++i) {
    unsigned char received;
    CHECK (read (10, &received, 1) == 1 && received == pattern[i]);
  }
  int status = -1;
  CHECK (waitpid (active_child, &status, 0) == active_child && status == 0);
  active_child = -1;
  CHECK (lseek (10, 0, SEEK_CUR) == sizeof (pattern));
  CHECK (close (10) == 0 && close (ready[0]) == 0 && close (go[1]) == 0);
  CHECK (unlink ("/g3_shared") == 0 && unlink ("/g3_moved/original") == 0);
  CHECK (rmdir ("/g3_held") == 0 && rmdir ("/g3_moved") == 0 && rmdir ("/g3_detached") == 0);
  puts ("GLIBC_FILES_EXTRA_PARENT_PASS shared_offset=512 child_positioned=256 dirs_reclaimed=3");
  return 0;
}
