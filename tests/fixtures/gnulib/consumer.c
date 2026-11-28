/* SPDX-License-Identifier: Apache-2.0 */
#include <config.h>
#include <stddef.h>
#include <wchar.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <signal.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <unistd.h>

#define check(value) do { if (!(value)) { \
  printf ("GNULIB_FAIL line=%d errno=%d\n", __LINE__, errno); return 1; \
} } while (0)

int
main (int argc, char **argv)
{
  (void) argc;
  const char *base = strrchr (argv[0], '/');
  base = base ? base + 1 : argv[0];
  check (strcmp (getprogname (), base) == 0);
  wint_t wide = L'X';
  check (wide != WEOF && sizeof (wint_t) >= 4 && O_BINARY == 0);
  check ((S_IRWXUGO & 0777) == 0777);

  struct sigaction action, saved_action;
  memset (&action, 0x5a, sizeof action);
  saved_action = action;
  errno = 0;
  check (sigaction (SIGINT, NULL, &action) == -1 && errno == ENOTSUP
         && !memcmp (&action, &saved_action, sizeof action));
  sigset_t signals, previous, saved_signals;
  check (sigemptyset (&signals) == 0 && sigaddset (&signals, SIGINT) == 0
         && sigismember (&signals, SIGINT) == 1);
  memset (&previous, 0x5a, sizeof previous); saved_signals = previous;
  errno = 0;
  check (sigprocmask (SIG_BLOCK, &signals, &previous) == -1 && errno == ENOTSUP
         && !memcmp (&previous, &saved_signals, sizeof previous));
  errno = 0;
  check (signal (SIGINT, SIG_IGN) == SIG_ERR && errno == ENOTSUP);

  struct rlimit limits = { 73, 74 };
  errno = EDOM;
  check (getrlimit (RLIMIT_NOFILE, &limits) == 0 && errno == EDOM);
  int capacity = getdtablesize ();
  check (capacity == 32 && limits.rlim_cur == (rlim_t) capacity
         && limits.rlim_max == (rlim_t) capacity);
  struct rlimit64 limits64;
  check (getrlimit64 (RLIMIT_NOFILE, &limits64) == 0
         && limits64.rlim_cur == limits.rlim_cur && limits64.rlim_max == limits.rlim_max);
  limits.rlim_cur = 73; limits.rlim_max = 74; errno = 0;
  check (getrlimit (RLIMIT_CPU, &limits) == -1 && errno == ENOSYS
         && limits.rlim_cur == 73 && limits.rlim_max == 74);
  errno = 0;
  check (getrlimit (RLIM_NLIMITS, &limits) == -1 && errno == EINVAL
         && limits.rlim_cur == 73 && limits.rlim_max == 74);

  struct stat plain, nofollow;
  check (stat ("/work/plain", &plain) == 0 && lstat ("/work/plain", &nofollow) == 0
         && S_ISREG (plain.st_mode) && nofollow.st_ino == plain.st_ino
         && nofollow.st_size == plain.st_size);
  int file = open ("/work/plain", O_RDONLY | O_BINARY);
  check (file >= 3);
  errno = 0;
  check (fdopendir (file) == NULL && errno == ENOTDIR);
  check (fcntl (file, F_GETFD) >= 0); /* Failure did not take ownership. */
  int aliases[32], count = 0;
  for (;;) {
    int fd = dup (file);
    if (fd < 0) { check (errno == EMFILE); break; }
    check (count < 32 && fd < capacity);
    aliases[count++] = fd;
  }
  check (count == capacity - 4);
  check (fcntl (file, F_DUPFD, capacity) == -1 && errno == EINVAL);
  for (int i = 0; i < count; ++i) check (close (aliases[i]) == 0);
  check (close (file) == 0);

  int directory_fd = open ("/work", O_RDONLY | O_DIRECTORY);
  check (directory_fd >= 3);
  DIR *directory = fdopendir (directory_fd);
  check (directory != NULL && dirfd (directory) == directory_fd);
  int seen = 0;
  struct dirent *entry;
  errno = 0;
  while ((entry = readdir (directory)) != NULL)
    if (!strcmp (entry->d_name, "plain")) seen = 1;
  check (seen && errno == 0 && closedir (directory) == 0);
  errno = 0;
  check (fcntl (directory_fd, F_GETFD) == -1 && errno == EBADF);
  printf ("GNULIB_XOS_OK progname wchar flags stat directory fd_limit=%d\n", capacity);
  return 0;
}
