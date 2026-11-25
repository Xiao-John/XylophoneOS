/* SPDX-License-Identifier: Apache-2.0
   Public API qualification against the complete, isolated glibc candidate. */
#define _GNU_SOURCE 1
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <sched.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#ifdef XOS_GLIBC_G3_EXEC_RECEIVER
static const struct { unsigned long magic; unsigned int version, size; }
  exec_marker __attribute__ ((section (".xos.exec"), used)) =
    { 0x3349424143455858UL, 3, 16 };
#endif

_Static_assert (sizeof (struct dirent) == 272 && sizeof (struct dirent64) == 272,
                "XOS LP64 directory entry layout");
_Static_assert (offsetof (struct dirent, d_name) == 12, "generic dirent field prefix");
static int checks;
#define CHECK(condition) do { ++checks; if (!(condition)) { \
  fprintf (stderr, "GLIBC_FILES_EXTRA_FAIL line=%d errno=%d\n", __LINE__, errno); \
  exit (1); } } while (0)

static int shared_fd;
static void *positioned_worker (void *argument)
{
  long index = (long) argument;
  char written[128], received[128];
  memset (written, (int) ('a' + index), sizeof (written));
  off_t offset = 4096 + index * 128;
  for (int round = 0; round < 64; ++round)
    {
      if (pwrite (shared_fd, written, sizeof (written), offset) != sizeof (written)
          || pread (shared_fd, received, sizeof (received), offset) != sizeof (received)
          || memcmp (received, written, sizeof (written)) != 0)
        return (void *) 1;
      sched_yield ();
    }
  return NULL;
}

static int inherited (void)
{
  char byte;
  struct stat original, detached;
  CHECK (fstat (12, &original) == 0 && fstat (14, &detached) == 0);
  DIR *moved = fdopendir (12), *removed = fdopendir (14);
  CHECK (moved != NULL && removed != NULL);
  CHECK (write (11, "R", 1) == 1 && read (13, &byte, 1) == 1 && byte == 'G');
  int seen = 0, count = 0;
  struct dirent *entry;
  errno = 0;
  while ((entry = readdir (moved)) != NULL)
    {
      if (!strcmp (entry->d_name, ".")) CHECK (entry->d_ino == original.st_ino);
      if (!strcmp (entry->d_name, "original")) ++seen;
      ++count;
    }
  CHECK (errno == 0 && count == 3 && seen == 1);
  count = 0;
  errno = 0;
  while ((entry = readdir (removed)) != NULL)
    {
      CHECK (!strcmp (entry->d_name, ".") || !strcmp (entry->d_name, ".."));
      if (!strcmp (entry->d_name, ".")) CHECK (entry->d_ino == detached.st_ino);
      ++count;
    }
  CHECK (errno == 0 && count == 2);
  CHECK (closedir (moved) == 0 && closedir (removed) == 0);
  puts ("GLIBC_FILES_EXTRA_INHERIT_DIR_PASS rename=stable deleted=retained");
  for (int round = 0; round < 256; ++round)
    {
      char data[8];
      CHECK (pwrite64 (10, "position", 8, 4096) == 8);
      CHECK (pread64 (10, data, 8, 4096) == 8 && !memcmp (data, "position", 8));
      sched_yield ();
    }
  CHECK (close (10) == 0 && close (11) == 0 && close (13) == 0);
  puts ("GLIBC_FILES_EXTRA_CHILD_PASS positioned_rounds=256");
  return 0;
}

static int normal (void)
{
  int fd = open ("/g3_positioned", O_CREAT | O_EXCL | O_RDWR, 0644);
  CHECK (fd >= 3);
  CHECK (write (fd, "abcdefgh", 8) == 8 && lseek (fd, 3, SEEK_SET) == 3);
  int alias = dup (fd);
  CHECK (alias >= 3);
  char data[8192];
  CHECK (pwrite (alias, "XY", 2, 0) == 2 && pread64 (alias, data, 8, 0) == 8);
  CHECK (!memcmp (data, "XYcdefgh", 8) && lseek64 (fd, 0, SEEK_CUR) == 3);
  CHECK (read (fd, data, 1) == 1 && data[0] == 'd');
  int append = open ("/g3_positioned", O_RDWR | O_APPEND);
  CHECK (append >= 3 && lseek (append, 2, SEEK_SET) == 2);
  CHECK (pwrite64 (append, "P", 1, 0) == 1 && lseek (append, 0, SEEK_CUR) == 2);
  CHECK (write (append, "!", 1) == 1 && lseek (append, 0, SEEK_CUR) == 9 && close (append) == 0);
  CHECK (pwrite (fd, "Z", 1, 4096) == 1);
  CHECK (pread (fd, data, sizeof (data), 9) == 3798);
  for (int i = 0; i < 3798; ++i) CHECK (data[i] == 0);
  CHECK (lseek (fd, 0, SEEK_CUR) == 4);
  CHECK (pwrite (fd, NULL, 0, 9000) == 0);
  struct stat information;
  CHECK (fstat (fd, &information) == 0 && information.st_size == 4097);
  errno = 0; CHECK (pread (fd, data, 1, -1) == -1 && errno == EINVAL);
  errno = 0; CHECK (pwrite (fd, data, 1, 0x100000000L) == -1 && errno == EOVERFLOW);
  int readonly = open ("/g3_positioned", O_RDONLY);
  errno = 0; CHECK (pwrite (readonly, "x", 1, 0) == -1 && errno == EBADF);
  CHECK (close (readonly) == 0);
  shared_fd = fd;
  CHECK (lseek (fd, 23, SEEK_SET) == 23);
  pthread_t workers[3];
  for (long i = 0; i < 3; ++i) CHECK (pthread_create (&workers[i], NULL, positioned_worker, (void *) i) == 0);
  for (int i = 0; i < 3; ++i) {
    void *result = (void *) 1;
    CHECK (pthread_join (workers[i], &result) == 0 && result == NULL);
  }
  CHECK (lseek (alias, 0, SEEK_CUR) == 23 && close (alias) == 0 && close (fd) == 0);
  puts ("GLIBC_FILES_EXTRA_POSITIONED_PASS aliases=shared append=explicit threads=3");

  for (int i = 0; i < 96; ++i) {
    char path[128];
    snprintf (path, sizeof (path), "/g3_enum/entry_%03d_目录", i);
    int item = open (path, O_CREAT | O_EXCL | O_RDWR, 0644);
    CHECK (item >= 3 && close (item) == 0);
  }
  char long_name[224], long_path[240];
  memset (long_name, 'a', 210); strcpy (long_name + 210, "_目录");
  snprintf (long_path, sizeof (long_path), "/g3_enum/%s", long_name);
  int long_fd = open (long_path, O_CREAT | O_EXCL | O_RDWR, 0644);
  CHECK (long_fd >= 3 && close (long_fd) == 0);
  errno = 0; CHECK (opendir ("/g3_positioned") == NULL && errno == ENOTDIR);
  errno = 0; CHECK (opendir ("/g3_absent") == NULL && errno == ENOENT);
  DIR *directory = opendir ("/g3_enum");
  CHECK (directory != NULL && (fcntl (dirfd (directory), F_GETFD) & FD_CLOEXEC));
  int directory_fd = dirfd (directory);
  CHECK (fstat (directory_fd, &information) == 0 && S_ISDIR (information.st_mode));
  int count = 0, long_seen = 0, sub_seen = 0;
  long cookie = -1;
  char resume[256] = {0};
  struct dirent *entry;
  errno = 0;
  while ((entry = readdir (directory)) != NULL) {
    CHECK (entry->d_ino != 0 && entry->d_namlen == strlen (entry->d_name));
    if (!strcmp (entry->d_name, ".")) CHECK (entry->d_ino == information.st_ino && entry->d_type == DT_DIR);
    if (!strcmp (entry->d_name, long_name)) ++long_seen;
    if (!strcmp (entry->d_name, "sub")) { ++sub_seen; CHECK (entry->d_type == DT_DIR); }
    if (entry->d_name[0] != '.') {
      char path[256]; struct stat file_stat;
      snprintf (path, sizeof (path), "/g3_enum/%s", entry->d_name);
      CHECK (stat (path, &file_stat) == 0 && file_stat.st_ino == entry->d_ino);
    }
    if (count == 50) cookie = telldir (directory);
    if (count == 51) strcpy (resume, entry->d_name);
    ++count;
  }
  CHECK (errno == 0 && count == 100 && long_seen == 1 && sub_seen == 1);
  errno = EBUSY; CHECK (readdir (directory) == NULL && errno == EBUSY);
  CHECK (cookie >= 0 && resume[0] != 0);
  seekdir (directory, cookie);
  entry = readdir (directory);
  CHECK (entry != NULL && !strcmp (entry->d_name, resume));
  rewinddir (directory);
  struct dirent copy, *copied = NULL;
  CHECK (readdir_r (directory, &copy, &copied) == 0 && copied == &copy && !strcmp (copy.d_name, "."));
  struct dirent64 copy64, *copied64 = NULL;
  CHECK (readdir64_r (directory, &copy64, &copied64) == 0 && copied64 == &copy64 && !strcmp (copy64.d_name, ".."));
  CHECK (closedir (directory) == 0);
  errno = 0; CHECK (fcntl (directory_fd, F_GETFD) == -1 && errno == EBADF);
  directory_fd = open ("/g3_enum", O_RDONLY | O_DIRECTORY);
  CHECK (directory_fd >= 3 && (directory = fdopendir (directory_fd)) != NULL);
  struct dirent64 *first64 = readdir64 (directory);
  CHECK (first64 != NULL && !strcmp (first64->d_name, ".") && closedir (directory) == 0);
  struct dirent **sorted = NULL;
  CHECK (scandir ("/g3_enum", &sorted, NULL, alphasort) == 100);
  for (int i = 1; i < 100; ++i) CHECK (strcmp (sorted[i - 1]->d_name, sorted[i]->d_name) < 0);
  for (int i = 0; i < 100; ++i) free (sorted[i]);
  free (sorted);
  puts ("GLIBC_FILES_EXTRA_DIRECTORY_PASS entries=100 identity=stat cookies=resume utf8=long scandir=sorted");
  DIR *streams[16];
  for (int i = 0; i < 16; ++i) CHECK ((streams[i] = opendir ("/g3_enum")) != NULL);
  errno = 0; CHECK (opendir ("/g3_enum") == NULL && errno == EMFILE);
  for (int i = 0; i < 16; ++i) CHECK (closedir (streams[i]) == 0);
  for (int i = 0; i < 64; ++i) CHECK ((directory = opendir ("/g3_enum")) != NULL && closedir (directory) == 0);
  for (int i = 0; i < 96; ++i) {
    char path[128]; snprintf (path, sizeof (path), "/g3_enum/entry_%03d_目录", i);
    CHECK (unlink (path) == 0);
  }
  CHECK (unlink (long_path) == 0 && unlink ("/g3_positioned") == 0);
  printf ("GLIBC_FILES_EXTRA_PASS checks=%d handle_quota=16 reuse=64\n", checks);
  return 0;
}

int main (int argc, char **argv)
{ return argc == 2 && !strcmp (argv[1], "inherited") ? inherited () : normal (); }
