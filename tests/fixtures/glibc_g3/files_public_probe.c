/* SPDX-License-Identifier: Apache-2.0
   Link against the complete candidate glibc, never the preview newlib sysroot.
   Run only on a private disposable test disk. */
#define _GNU_SOURCE 1
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#ifdef XOS_GLIBC_G3_EXEC_RECEIVER
/* Opt in only for the qualified receiver fixture; G2 images have no global
   exec claim. The loader requires this allocated, read-only section. */
static const struct { unsigned long magic; unsigned int version, size; }
  exec_marker __attribute__ ((section (".xos.exec"), used)) =
    { 0x3349424143455858UL, 3, 16 };
#endif

static int checks;
#define CHECK(condition) do { ++checks; if (!(condition)) { \
  fprintf (stderr, "GLIBC_G3_FILES_FAIL line=%d errno=%d\n", __LINE__, errno); \
  exit (1); } } while (0)
static const char path[] = "/glibc_g3_files_probe.tmp";
static int shared_fd;
static const char inherited_path[] = "/glibc_g3_inherit.tmp";
static const char cloexec_path[] = "/glibc_g3_cloexec.tmp";

static int descriptor_argument (const char *text)
{
  char *end = 0;
  const long value = strtol (text, &end, 10);
  CHECK (end != text && *end == 0 && value >= 3 && value < 32);
  return (int) value;
}

static int inherit (int argc, char **argv)
{
  CHECK (argc == 7);
  const int original = descriptor_argument (argv[2]);
  const int alias = descriptor_argument (argv[3]);
  const int clo_alias = descriptor_argument (argv[4]);
  const int clo_only = descriptor_argument (argv[5]);
  const int high_alias = descriptor_argument (argv[6]);
  errno = 0;
  CHECK (fcntl (clo_alias, F_GETFD) == -1 && errno == EBADF);
  errno = 0;
  CHECK (fcntl (clo_only, F_GETFD) == -1 && errno == EBADF);
  CHECK (fcntl (original, F_GETFD) == 0 && fcntl (alias, F_GETFD) == 0);
  CHECK (fcntl (high_alias, F_GETFD) == 0);
  CHECK (lseek (original, 0, SEEK_CUR) == 2);
  char data[3] = { 0 };
  CHECK (read (original, data, 2) == 2 && memcmp (data, "23", 2) == 0);
  CHECK (read (alias, data, 2) == 2 && memcmp (data, "45", 2) == 0);
  CHECK (lseek (high_alias, 0, SEEK_CUR) == 6);
  CHECK (close (original) == 0);
  CHECK (read (alias, data, 2) == 2 && memcmp (data, "67", 2) == 0);
  CHECK (close (alias) == 0);
  CHECK (read (high_alias, data, 2) == 2 && memcmp (data, "89", 2) == 0);
  struct stat information;
  CHECK (fstat (high_alias, &information) == 0 && information.st_size == 10);
  CHECK (close (high_alias) == 0);
  /* The files session has 16 handles. Filling all 16 after the retained object
     closes also verifies cleanup of the CLOEXEC-only remote description. */
  int handles[16];
  for (int i = 0; i < 16; ++i)
    { handles[i] = open (inherited_path, O_RDONLY); CHECK (handles[i] >= 3); }
  errno = 0;
  CHECK (open (inherited_path, O_RDONLY) == -1 && errno == EMFILE);
  for (int i = 0; i < 16; ++i) CHECK (close (handles[i]) == 0);
  CHECK (unlink (inherited_path) == 0 && unlink (cloexec_path) == 0);
  printf ("GLIBC_G3_FILES_INHERIT_PASS checks=%d shared_offset=10 cloexec=2 quota=16\n", checks);
  return 0;
}

static int service_death (void)
{
  int fd = open (path, O_CREAT | O_EXCL | O_RDWR, 0644);
  CHECK (fd >= 3 && write (fd, "alive", 5) == 5);
  printf ("GLIBC_G3_FILES_DEATH_READY fd=%d\n", fd);
  CHECK (fflush (stdout) == 0);
  char byte;
  /* Only a separately marked fault image implements this exact path trigger.
     The production files service handles it as an ordinary absent pathname. */
  errno = 0;
  CHECK (open ("/.glibc_g3_service_death", O_RDONLY) == -1 && errno == EIO);
  const int first_error = errno;
  CHECK (first_error == EIO);
  for (int i = 0; i < 32; ++i)
    {
      errno = 0; CHECK (lseek (fd, 0, SEEK_SET) == -1 && errno == EIO);
      errno = 0; CHECK (read (fd, &byte, 1) == -1 && errno == EIO);
      errno = 0; CHECK (write (fd, "x", 1) == -1 && errno == EIO);
    }
  struct stat information;
  errno = 0; CHECK (fstat (fd, &information) == -1 && errno == EIO);
  errno = 0; CHECK (open (path, O_RDONLY) == -1 && errno == EIO);
  errno = 0; CHECK (close (fd) == -1 && errno == EIO);
  errno = 0; CHECK (close (fd) == -1 && errno == EBADF);
  printf ("GLIBC_G3_FILES_DEATH_PASS checks=%d first_errno=%d sticky_errno=%d\n",
          checks, first_error, EIO);
  return 0;
}

static void *writer (void *opaque)
{
  const char value = (char) (long) opaque;
  for (int i = 0; i < 64; ++i)
    if (write (shared_fd, &value, 1) != 1) return (void *) 1;
  return 0;
}

int main (int argc, char **argv)
{
  if (argc > 1 && strcmp (argv[1], "inherit") == 0) return inherit (argc, argv);
  if (argc > 1 && strcmp (argv[1], "service-death") == 0) return service_death ();
  const int threaded = argc < 2 || strcmp (argv[1], "single") != 0;
  errno = 0;
  CHECK (read (-1, 0, 0) == -1 && errno == EBADF);
  errno = 0;
  CHECK (open ("/glibc_g3_missing_file", O_RDONLY) == -1 && errno == ENOENT);
  int fd = open (path, O_CREAT | O_EXCL | O_RDWR | O_CLOEXEC, 0644);
  CHECK (fd >= 3);
  CHECK (fcntl (fd, F_GETFD) == FD_CLOEXEC);
  CHECK (write (fd, "abcdef", 6) == 6);
  int copy = dup (fd);
  CHECK (copy >= 3 && copy != fd && fcntl (copy, F_GETFD) == 0);
  CHECK (lseek (copy, 0, SEEK_SET) == 0);
  char data[8] = { 0 };
  CHECK (read (fd, data, 2) == 2 && memcmp (data, "ab", 2) == 0);
  CHECK (read (copy, data, 2) == 2 && memcmp (data, "cd", 2) == 0);
  CHECK (close (fd) == 0);
  CHECK (read (copy, data, 4) == 2 && memcmp (data, "ef", 2) == 0);
  struct stat information;
  CHECK (fstat (copy, &information) == 0 && information.st_size == 6
         && S_ISREG (information.st_mode) && information.st_ino != 0);
  CHECK (fsync (copy) == 0 && close (copy) == 0);
  FILE *stream = fopen (path, "w+");
  CHECK (stream != 0);
  unsigned char input[7000], output[7000];
  for (size_t i = 0; i < sizeof (input); ++i) input[i] = (unsigned char) (i * 37);
  CHECK (fwrite (input, 1, sizeof (input), stream) == sizeof (input));
  CHECK (fflush (stream) == 0 && fseek (stream, 0, SEEK_SET) == 0);
  CHECK (fread (output, 1, sizeof (output), stream) == sizeof (output));
  CHECK (memcmp (input, output, sizeof (input)) == 0);
  CHECK (fclose (stream) == 0);
  shared_fd = open (path, O_WRONLY | O_TRUNC);
  CHECK (shared_fd >= 3);
  if (threaded)
    {
      pthread_t threads[3];
      for (int i = 0; i < 3; ++i) CHECK (pthread_create (&threads[i], 0, writer, (void *) (long) ('a' + i)) == 0);
      for (int i = 0; i < 3; ++i)
        { void *result = 0; CHECK (pthread_join (threads[i], &result) == 0 && result == 0); }
      CHECK (fstat (shared_fd, &information) == 0 && information.st_size == 192);
    }
  else CHECK (write (shared_fd, "single", 6) == 6);
  CHECK (close (shared_fd) == 0);
  CHECK (unlink (path) == 0);
  errno = 0;
  CHECK (open (path, O_RDONLY) == -1 && errno == ENOENT);
  printf ("GLIBC_G3_FILES_PASS checks=%d threaded=%d\n", checks, threaded);
  return 0;
}
