/* SPDX-License-Identifier: Apache-2.0 */
/* Exercise files readiness with actual endpoints and glibc file calls. */
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "xos_file_session.h"
#include "xos_file_trap.h"

#define CHECK(expression) do { if (!(expression)) { \
  printf ("FILE_REPLY_WAIT_FAIL line=%d errno=%d\n", __LINE__, errno); exit (1); \
} } while (0)

enum { wait_mode = 4, wait_timeout = -13, wait_broken = -7 };
static const xos_u64 tick = 10000000ULL;
static xos_u32 handles[2];
static xos_u32 sequence;
static atomic_int waiter_entered, waiter_done;
static long waiter_result;

static xos_u64
now (void)
{
  long value = file_trap (46, 0, 0, 0);
  CHECK (value >= 0);
  return (xos_u64) value;
}

static long
wait_reply (xos_u32 handle, xos_u64 deadline)
{
  return file_trap (85, handle, wait_mode, deadline);
}

static void
send_request (const char *path)
{
  struct xos_file_request request = {0};
  request.magic = 0x51455246;
  request.version = 2;
  request.request_id = ++sequence;
  request.operation = path == NULL ? 1 : file_open;
  if (path != NULL)
    {
      request.name_length = (xos_u32) strlen (path);
      memcpy (request.name, path, request.name_length + 1);
      request.flags = 1; /* read-only */
    }
  CHECK (file_trap (4, handles[0], (xos_u64) &request, sizeof (request)) == 0);
}

static void
consume_ping (void)
{
  struct xos_file_response response;
  CHECK (file_trap (5, handles[1], (xos_u64) &response, sizeof (response)) == sizeof (response));
  CHECK (response.magic == 0x53455246 && response.version == 2
         && response.request_id == sequence && response.status_code == 0
         && response.length == 0);
}

static void *
wait_in_thread (void *unused)
{
  (void) unused;
  xos_u64 deadline = now () + 200 * tick;
  atomic_store (&waiter_entered, 1);
  waiter_result = wait_reply (handles[1], deadline);
  atomic_store (&waiter_done, 1);
  return NULL;
}

static void
send_to_waiter (const char *path, long expected)
{
  pthread_t thread;
  CHECK (pthread_create (&thread, NULL, wait_in_thread, NULL) == 0);
  const xos_u64 deadline = now () + 100 * tick;
  while (!atomic_load (&waiter_entered))
    {
      CHECK (now () < deadline);
      CHECK (file_trap (47, now () + tick, 0, 0) == 0);
    }
  CHECK (file_trap (47, now () + 3 * tick, 0, 0) == 0);
  CHECK (!atomic_load (&waiter_done));
  xos_u64 started = now ();
  send_request (path);
  CHECK (pthread_join (thread, NULL) == 0);
  CHECK (waiter_result == expected);
  printf ("FILE_REPLY_WAKE result=%ld elapsed_ns=%llu\n",
          waiter_result, (unsigned long long) (now () - started));
}

static void *
concurrent_read (void *context)
{
  int fd = *(const int *) context;
  for (int round = 0; round < 64; ++round)
    {
      char data[8];
      if (pread (fd, data, sizeof (data), 0) != (ssize_t) sizeof (data)
          || memcmp (data, "XOS-read", sizeof (data)) != 0)
        return (void *) 1;
    }
  return NULL;
}

int
main (int argc, char **argv)
{
  CHECK (argc == 2);
  if (strcmp (argv[1], "concurrent") == 0)
    {
      int fd = open ("/bin/wait.txt", O_RDONLY);
      CHECK (fd >= 3);
      pthread_t peers[2];
      for (int index = 0; index < 2; ++index)
        CHECK (pthread_create (&peers[index], NULL, concurrent_read, &fd) == 0);
      for (int index = 0; index < 2; ++index)
        {
          void *result;
          CHECK (pthread_join (peers[index], &result) == 0 && result == NULL);
        }
      CHECK (lseek (fd, 0, SEEK_CUR) == 0 && close (fd) == 0);
      puts ("FILE_REPLY_WAIT_PASS concurrent reads=128 offset=0");
      return 0;
    }
  CHECK (file_trap (22, (xos_u64) handles, 0, 0) == 0);
  CHECK (handles[0] != 0 && handles[1] != 0 && handles[0] != handles[1]);
  CHECK (wait_reply (handles[0], now () + tick) == -1);
  CHECK (wait_reply (handles[1], 0) == -2);
  if (strcmp (argv[1], "normal") == 0)
    {
      send_request (NULL);
      CHECK (file_trap (47, now () + 3 * tick, 0, 0) == 0);
      CHECK (wait_reply (handles[1], now ()) == wait_timeout);
      xos_u64 start = now ();
      CHECK (wait_reply (handles[1], start + 20 * tick) == 0);
      CHECK (now () - start <= tick);
      consume_ping ();
      xos_u64 deadline = now () + 5 * tick;
      CHECK (wait_reply (handles[1], deadline) == wait_timeout);
      CHECK (now () >= deadline);
      send_to_waiter (NULL, 0);
      consume_ping ();
      puts ("FILE_REPLY_WAIT_PASS normal queued=1 expired=1 blocked=1");
    }
  else if (strcmp (argv[1], "death") == 0)
    {
      send_to_waiter ("/.glibc_g3_service_death", wait_broken);
      CHECK (wait_reply (handles[1], now () + tick) == -1);
      puts ("FILE_REPLY_WAIT_PASS death blocked=1 old_handle_denied=1");
    }
  else if (strcmp (argv[1], "death_libc") == 0)
    {
      errno = 0;
      CHECK (open ("/.glibc_g3_service_death", O_RDONLY) == -1 && errno == EIO);
      errno = 0;
      CHECK (open ("/bin/wait.txt", O_RDONLY) == -1 && errno == EIO);
      puts ("FILE_REPLY_WAIT_PASS death_libc sticky_eio=1");
    }
  else if (strcmp (argv[1], "cancel") == 0)
    {
      puts ("FILE_REPLY_WAIT_CANCEL_READY");
      CHECK (fflush (stdout) == 0);
      (void) wait_reply (handles[1], now () + 3000 * tick);
      CHECK (0);
    }
  else
    CHECK (0);
  return 0;
}
