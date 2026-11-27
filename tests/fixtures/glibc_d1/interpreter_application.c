/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdlib.h>
#include <string.h>
#include <sys/auxv.h>
#include <unistd.h>

static volatile int initialized;

static void __attribute__ ((constructor))
initialize (void)
{
  initialized = 17;
}

static void *
run_worker (void *argument)
{
  return argument;
}

int
main (int argc, char **argv)
{
  if (argc != 2 || strcmp (argv[1], "ordinary") != 0 || initialized != 17
      || getauxval (AT_PAGESZ) != 4096)
    return 31;
  const char *value = getenv ("D1_ENTRY_ENV");
  if (value == NULL || strcmp (value, "verified") != 0)
    return 32;
  char *data = malloc (16);
  if (data == NULL)
    return 33;
  const int fd = open ("/tests/input", O_RDONLY);
  const int acquired = fd >= 0 && read (fd, data, 4) == 4
                       && memcmp (data, "ABCD", 4) == 0;
  const int closed = fd >= 0 && close (fd) == 0;
  free (data);
  if (!acquired || !closed || close (-1) != -1 || errno != EBADF)
    return 34;
  pthread_t worker = 0;
  if (pthread_create (&worker, NULL, run_worker, NULL) != ENOTSUP || worker != 0)
    return 36;
  static const char marker[] =
    "D1_DYNAMIC_C_OK ctor=1 env=1 auxv=1 file=1 errno=1 worker_unwinder=required\n";
  return write (STDOUT_FILENO, marker, sizeof (marker) - 1) == sizeof (marker) - 1 ? 0 : 35;
}
