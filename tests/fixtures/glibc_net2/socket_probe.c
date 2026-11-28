// SPDX-License-Identifier: Apache-2.0
#define _GNU_SOURCE 1
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <poll.h>
#include <pthread.h>
#include <sched.h>
#include <stdint.h>
#include <time.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

_Static_assert (TCP_NODELAY == 1 && TCP_MAXSEG == 2, "public TCP option numbers");
_Static_assert (sizeof (struct tcphdr) == 20, "public TCP header size");
_Static_assert (offsetof (struct tcphdr, th_flags) == 13, "public TCP header flags offset");

#define CHECK(expr) do { if (!(expr)) { \
  fprintf (stderr, "GLIBC_NET2_FAIL line=%d errno=%d\n", __LINE__, errno); exit (1); \
} } while (0)

static int
dial (int fd, uint32_t host, unsigned int port)
{
  const struct sockaddr_in address = {
    .sin_family = AF_INET, .sin_addr = { htonl (host) }, .sin_port = htons (port) };
  return connect (fd, (const struct sockaddr *) &address, sizeof (address));
}

static void
exercise_stream (unsigned int port, const char *nonce, int legacy)
{
  CHECK (strlen (nonce) == 32);
  int fd = socket (AF_INET, SOCK_STREAM | SOCK_CLOEXEC, IPPROTO_TCP);
  CHECK (fd >= 0 && fcntl (fd, F_GETFD) == FD_CLOEXEC);
  struct stat info;
  CHECK (fstat (fd, &info) == 0 && S_ISSOCK (info.st_mode));
  CHECK (lseek (fd, 0, SEEK_SET) == -1 && errno == ESPIPE);
  CHECK (fcntl (fd, F_SETFL, O_RDWR | O_NONBLOCK) == 0);
  CHECK ((fcntl (fd, F_GETFL) & O_NONBLOCK) != 0);
  CHECK (fcntl (fd, F_SETFL, O_RDWR) == 0);
  CHECK (dial (fd, 0x0a000202, port) == 0);
  CHECK (dial (fd, 0x0a000202, port) == -1 && errno == EISCONN);
  if (legacy)
    {
      struct pollfd pending = { .fd = fd, .events = POLLOUT };
      CHECK (poll (&pending, 1, 40) == -1 && errno == EOPNOTSUPP);
      CHECK (shutdown (fd, SHUT_WR) == -1 && errno == EOPNOTSUPP);
    }
  CHECK (send (fd, nonce, 32, MSG_DONTWAIT) == -1 && errno == EOPNOTSUPP);
  CHECK (fork () == -1 && errno == ENOTSUP);
  int duplicate = dup (fd);
  CHECK (duplicate >= 0 && fcntl (duplicate, F_GETFD) == 0);
  CHECK (close (fd) == 0);
  int reused = socket (AF_INET, SOCK_STREAM, 0);
  CHECK (reused == fd);
  CHECK (send (reused, nonce, 32, 0) == -1 && errno == ENOTCONN);
  CHECK (close (reused) == 0);

  size_t sent = 0;
  while (sent < 32)
    {
      ssize_t n = send (duplicate, nonce + sent, 32 - sent, MSG_NOSIGNAL);
      CHECK (n > 0);
      sent += n;
    }
  unsigned char data[33];
  ssize_t first = recv (duplicate, data, sizeof (data), 0);
  CHECK (first > 0 && first <= 32);
  size_t read_bytes = first;
  while (read_bytes < 32)
    {
      ssize_t n = read (duplicate, data + read_bytes, 32 - read_bytes);
      CHECK (n > 0);
      read_bytes += n;
    }
  CHECK (read (duplicate, data + 32, 1) == 0);
  CHECK (recv (duplicate, data + 32, 1, 0) == 0);
  printf ("GLIBC_NET2_STREAM nonce=%s data=", nonce);
  for (size_t i = 0; i < read_bytes; ++i) printf ("%02x", data[i]);
  puts ("");

  unsigned char tail[1537];
  for (size_t i = 0; i < sizeof (tail); ++i) tail[i] = nonce[i % 32];
  ssize_t short_write = write (duplicate, tail, sizeof (tail));
  CHECK (short_write > 0 && short_write < (ssize_t) sizeof (tail));
  sent = short_write;
  while (sent < sizeof (tail))
    {
      ssize_t n = write (duplicate, tail + sent, sizeof (tail) - sent);
      CHECK (n > 0);
      sent += n;
    }
  CHECK (close (duplicate) == 0);
  CHECK (close (duplicate) == -1 && errno == EBADF);
}

static void
exercise_half_close (unsigned int port, const char *nonce)
{
  CHECK (strlen (nonce) == 32);
  int fd = socket (AF_INET, SOCK_STREAM, 0);
  CHECK (fd >= 0 && dial (fd, 0x0a000202, port) == 0);
  struct pollfd pending = { .fd = fd, .events = POLLOUT };
  CHECK (poll (&pending, 1, 0) == 1 && (pending.revents & POLLOUT));
  CHECK (poll (&pending, 1, 5000) == 1 && (pending.revents & POLLOUT));
  pending.events = POLLIN;
  struct timespec before, after;
  CHECK (clock_gettime (CLOCK_MONOTONIC, &before) == 0);
  CHECK (poll (&pending, 1, 30) == 0 && !pending.revents);
  CHECK (clock_gettime (CLOCK_MONOTONIC, &after) == 0);
  long elapsed = (after.tv_sec - before.tv_sec) * 1000000000L + after.tv_nsec - before.tv_nsec;
  CHECK (elapsed >= 30000000L && elapsed < 3000000000L);
  CHECK (send (fd, nonce, 32, 0) == 32);
  int duplicate = dup (fd);
  CHECK (duplicate >= 0 && shutdown (duplicate, SHUT_WR) == 0 && shutdown (fd, SHUT_WR) == 0);
  CHECK (send (fd, nonce, 1, MSG_NOSIGNAL) == -1 && errno == EPIPE);
  CHECK (write (duplicate, nonce, 1) == -1 && errno == EPIPE);
  CHECK (close (fd) == 0);
  int reused = socket (AF_INET, SOCK_STREAM, 0);
  CHECK (reused == fd);
  struct pollfd descriptors[3] = {
    { .fd = duplicate, .events = POLLIN }, { .fd = -1, .events = POLLIN }, { .fd = 1000, .events = POLLIN } };
  CHECK (poll (descriptors, 3, 5000) >= 1 && (descriptors[2].revents & POLLNVAL) && !descriptors[1].revents);
  descriptors[2].fd = -1;
  CHECK (poll (descriptors, 3, 5000) == 1 && (descriptors[0].revents & POLLIN));
  unsigned char data[33]; size_t received = 0;
  while (received < 32)
    {
      ssize_t count = recv (duplicate, data + received, 32 - received, 0);
      CHECK (count > 0); received += count;
    }
  CHECK (poll (descriptors, 3, 5000) == 1 && (descriptors[0].revents & (POLLIN | POLLHUP)) == (POLLIN | POLLHUP));
  CHECK (recv (duplicate, data + 32, 1, 0) == 0);
  printf ("GLIBC_NET2_STREAM nonce=%s data=", nonce);
  for (size_t i = 0; i < received; ++i) printf ("%02x", data[i]);
  puts ("");
  CHECK (close (duplicate) == 0 && close (reused) == 0);
}

static void
exercise_stalled_peer (const char *pid)
{
  CHECK (setenv ("XOS_NET_SERVICE_PID", pid, 1) == 0);
  int fd = socket (AF_INET, SOCK_STREAM, 0);
  CHECK (fd >= 0 && dial (fd, 0x0a000202, 9) == 0);
  struct pollfd pending = { .fd = fd, .events = POLLOUT };
  struct timespec before, after;
  CHECK (clock_gettime (CLOCK_MONOTONIC, &before) == 0);
  CHECK (poll (&pending, 1, 0) == -1 && errno == EAGAIN && !pending.revents);
  CHECK (clock_gettime (CLOCK_MONOTONIC, &after) == 0);
  CHECK ((after.tv_sec - before.tv_sec) * 1000000000L + after.tv_nsec - before.tv_nsec < 700000000L);
  int file = open ("/tmp/p1h_mixed", O_CREAT | O_RDWR | O_TRUNC, 0600);
  int pipes[2];
  CHECK (file >= 0 && pipe2 (pipes, O_NONBLOCK) == 0 && write (pipes[1], "x", 1) == 1);
  struct pollfd mixed[4] = { pending, { .fd = file, .events = POLLIN },
    { .fd = pipes[0], .events = POLLIN }, { .fd = pipes[1], .events = POLLOUT } };
  CHECK (clock_gettime (CLOCK_MONOTONIC, &before) == 0);
  CHECK (poll (mixed, 4, 2500) == 3 && !mixed[0].revents && mixed[1].revents == POLLIN &&
         mixed[2].revents == POLLIN && mixed[3].revents == POLLOUT);
  CHECK (clock_gettime (CLOCK_MONOTONIC, &after) == 0);
  CHECK ((after.tv_sec - before.tv_sec) * 1000000000L + after.tv_nsec - before.tv_nsec < 700000000L);
  CHECK (close (file) == 0 && close (pipes[0]) == 0 && close (pipes[1]) == 0);
  puts ("GLIBC_NET2_MIXED_READY_PROMPT");
  CHECK (clock_gettime (CLOCK_MONOTONIC, &before) == 0);
  CHECK (poll (&pending, 1, 40) == 0 && !pending.revents);
  CHECK (clock_gettime (CLOCK_MONOTONIC, &after) == 0);
  long elapsed = (after.tv_sec - before.tv_sec) * 1000000000L + after.tv_nsec - before.tv_nsec;
  CHECK (elapsed >= 40000000L && elapsed < 700000000L);
  printf ("GLIBC_NET2_POLL_TIMEOUT elapsed_ns=%ld\n", elapsed);
  CHECK (poll (&pending, 1, 2500) == 1 && pending.revents == POLLOUT);
  CHECK (close (fd) == 0);
}

static void
exercise_pipe_poll (void)
{
  int pipes[2]; CHECK (pipe2 (pipes, O_NONBLOCK) == 0);
  struct pollfd items[2] = { { .fd = pipes[0], .events = POLLIN }, { .fd = pipes[1], .events = POLLOUT } };
  CHECK (poll (items, 2, 0) == 1 && !items[0].revents && items[1].revents == POLLOUT);
  unsigned char bytes[4096]; memset (bytes, 0x39, sizeof (bytes));
  CHECK (write (pipes[1], bytes, sizeof (bytes)) == sizeof (bytes));
  CHECK (poll (items, 2, 0) == 1 && items[0].revents == POLLIN && !items[1].revents);
  unsigned char output[4096];
  CHECK (read (pipes[0], output, sizeof (output)) == sizeof (output) && !memcmp (bytes, output, sizeof (bytes)));
  CHECK (close (pipes[1]) == 0);
  CHECK (poll (items, 2, 0) == 2 && items[0].revents == (POLLIN | POLLHUP) && items[1].revents == POLLNVAL);
  CHECK (read (pipes[0], output, 1) == 0 && close (pipes[0]) == 0);
  CHECK (pipe2 (pipes, O_NONBLOCK) == 0 && close (pipes[0]) == 0);
  items[0] = (struct pollfd) { .fd = pipes[1], .events = POLLOUT };
  CHECK (poll (items, 1, 0) == 1 && items[0].revents == POLLERR);
  CHECK (write (pipes[1], bytes, 1) == -1 && errno == EPIPE && close (pipes[1]) == 0);
}

static void
exercise_capacity (void)
{
  struct pollfd ignored = { .fd = -1, .events = POLLIN };
  CHECK (poll (&ignored, 1, 0) == 0 && !ignored.revents);
  CHECK (poll (NULL, 0, 0) == 0);
  struct pollfd invalid = { .fd = 1000, .events = POLLIN };
  CHECK (poll (&invalid, 1, 0) == 1 && invalid.revents == POLLNVAL);
  int descriptors[32];
  size_t count = 0;
  while (count < sizeof (descriptors) / sizeof (descriptors[0]))
    {
      int fd = socket (AF_INET, SOCK_STREAM, 0);
      if (fd < 0) break;
      descriptors[count++] = fd;
    }
  CHECK (count > 0 && count < sizeof (descriptors) / sizeof (descriptors[0]));
  CHECK (socket (AF_INET, SOCK_STREAM, 0) == -1 && errno == EMFILE);
  CHECK (close (descriptors[count - 1]) == 0);
  CHECK (socket (AF_INET, SOCK_STREAM, 0) == descriptors[count - 1]);
  for (size_t i = 0; i < count; ++i) CHECK (close (descriptors[i]) == 0);
}

static uint64_t clock_ns (void)
{
  struct timespec now; CHECK (clock_gettime (CLOCK_MONOTONIC, &now) == 0);
  return (uint64_t) now.tv_sec * 1000000000ULL + now.tv_nsec;
}
static void exercise_nonblocking (unsigned int port, const char *nonce, int refused)
{
  int fd = socket (AF_INET, SOCK_STREAM | SOCK_NONBLOCK, 0);
  CHECK (fd >= 0);
  int result = dial (fd, 0x0a000202, port);
  if (refused && result == -1 && errno == ECONNREFUSED) { CHECK (close (fd) == 0); return; }
  CHECK (result == 0 || (result == -1 && errno == EINPROGRESS));
  struct pollfd pending = { .fd = fd, .events = POLLOUT };
  CHECK (poll (&pending, 1, 5000) == 1);
  int error = -1; socklen_t length = sizeof (error);
  CHECK (getsockopt (fd, SOL_SOCKET, SO_ERROR, &error, &length) == 0 && length == sizeof (error));
  if (refused) { CHECK (error == ECONNREFUSED || error == ECONNRESET); CHECK (close (fd) == 0); return; }
  CHECK (error == 0 && (pending.revents & POLLOUT));
  char data[32];
  CHECK (recv (fd, data, sizeof (data), 0) == -1 && errno == EAGAIN);
  CHECK (send (fd, nonce, 32, 0) == 32);
  pending.events = POLLIN;
  CHECK (poll (&pending, 1, 5000) == 1 && (pending.revents & POLLIN));
  size_t received = 0;
  while (received < sizeof (data)) {
    ssize_t count = recv (fd, data + received, sizeof (data) - received, 0);
    if (count == -1 && errno == EAGAIN) { CHECK (poll (&pending, 1, 5000) == 1); continue; }
    CHECK (count > 0); received += count;
  }
  CHECK (shutdown (fd, SHUT_RDWR) == 0);
  CHECK (recv (fd, data, 1, 0) == 0);
  CHECK (send (fd, data, 1, MSG_NOSIGNAL) == -1 && errno == EPIPE);
  CHECK (close (fd) == 0);
}
static void exercise_read_close (unsigned int port, const char *nonce)
{
  int fd = socket (AF_INET, SOCK_STREAM, 0);
  CHECK (fd >= 0 && dial (fd, 0x0a000202, port) == 0);
  CHECK (shutdown (fd, SHUT_RD) == 0 && shutdown (fd, SHUT_RD) == 0);
  CHECK (send (fd, nonce, 32, 0) == 32);
  char byte = 0;
  CHECK (read (fd, &byte, 1) == 0);
  struct pollfd pending = { .fd = fd, .events = POLLIN | POLLOUT };
  CHECK (poll (&pending, 1, 0) == 1 && (pending.revents & (POLLIN | POLLHUP)) == (POLLIN | POLLHUP));
  CHECK (shutdown (fd, SHUT_WR) == 0);
  CHECK (close (fd) == 0);
}
static void exercise_window (unsigned int port, const char *nonce)
{
  CHECK (strlen (nonce) == 32);
  int fd = socket (AF_INET, SOCK_STREAM | SOCK_NONBLOCK, 0);
  CHECK (fd >= 0);
  // The packet peer withholds its SYN/ACK until this serial barrier. The
  // pending state is therefore observed, not inferred from a fast connection.
  CHECK (dial (fd, 0x0a000202, port) == -1 && errno == EINPROGRESS);
  CHECK (dial (fd, 0x0a000202, port) == -1 && errno == EALREADY);
  puts ("GLIBC_NET2_CONNECT_PENDING");
  struct pollfd pending = { .fd = fd, .events = POLLOUT };
  CHECK (poll (&pending, 1, 5000) == 1 && (pending.revents & POLLOUT));
  int error = -1; socklen_t length = sizeof (error);
  CHECK (getsockopt (fd, SOL_SOCKET, SO_ERROR, &error, &length) == 0 && !error);
  CHECK (send (fd, nonce, 32, 0) == 32);
  pending.events = POLLIN;
  CHECK (poll (&pending, 1, 5000) == 1 && (pending.revents & POLLIN));
  CHECK (poll (&pending, 1, 0) == 1 && (pending.revents & POLLIN));
  unsigned char challenge[32]; size_t received = 0;
  while (received < sizeof (challenge)) {
    ssize_t count = recv (fd, challenge + received, sizeof (challenge) - received, 0);
    CHECK (count > 0); received += count;
  }
  int immediate = poll (&pending, 1, 0);
  CHECK ((immediate == 0 || (immediate == -1 && errno == EAGAIN)) && !pending.revents);
  unsigned char data[512];
  for (size_t i = 0; i < sizeof (data); ++i) data[i] = nonce[i % 32];
  size_t queued = 0;
  for (;;) {
    ssize_t count = send (fd, data, sizeof (data), 0);
    if (count < 0) { CHECK (errno == EAGAIN); break; }
    CHECK (count > 0); queued += count; CHECK (queued <= 32768);
  }
  CHECK (queued > 0);
  pending.events = POLLOUT;
  immediate = poll (&pending, 1, 0);
  CHECK ((immediate == 0 || (immediate == -1 && errno == EAGAIN)) && !pending.revents);
  CHECK (poll (&pending, 1, 40) == 0 && !pending.revents);
  printf ("GLIBC_NET2_WINDOW_BLOCKED queued=%lu\n", (unsigned long) queued);
  CHECK (poll (&pending, 1, 5000) == 1 && (pending.revents & POLLOUT));
  CHECK (poll (&pending, 1, 0) == 1 && (pending.revents & POLLOUT));
  CHECK (close (fd) == 0);
  puts ("GLIBC_NET2_WINDOW_RESTORED");
}
struct poll_worker_context { int fd; unsigned int entered, done; int result, error; short revents; uint64_t elapsed; };
static void *poll_worker (void *argument)
{
  struct poll_worker_context *context = argument;
  struct pollfd pending = { .fd = context->fd, .events = POLLIN };
  uint64_t began = clock_ns ();
  __atomic_store_n (&context->entered, 1, __ATOMIC_RELEASE);
  context->result = poll (&pending, 1, 750);
  context->error = errno; context->revents = pending.revents;
  context->elapsed = clock_ns () - began;
  __atomic_store_n (&context->done, 1, __ATOMIC_RELEASE);
  return NULL;
}
static long native_trap (uint64_t number, uint64_t a, uint64_t b)
{
  register uint64_t result __asm__ ("rax") = number;
  __asm__ volatile ("int $0x80" : "+a" (result) : "D" (a), "S" (b), "d" (0ULL) : "memory", "cc");
  return (long) result;
}
static long reserve_fragment (uint32_t operation, uint64_t address)
{
  struct { uint32_t version, size, operation, flags; uint64_t address, length, alignment;
    uint32_t protection, reserved0; uint64_t reserved1, reserved2; } request =
    { 1, 64, operation, operation == 1 ? 1 : 0, address, 4096, operation == 1 ? 4096 : 0, 0, 0, 0, 0 };
  return native_trap (67, (uint64_t) &request, 0);
}
static void exercise_deferred_release (unsigned int port)
{
  const uint64_t page = 0x100000a00000ULL, arena = 0x100070000000ULL;
  int fd = socket (AF_INET, SOCK_STREAM, 0);
  CHECK (fd >= 0 && dial (fd, 0x0a000202, port) == 0);
  CHECK (reserve_fragment (1, page - 4096) == (long) (page - 4096));
  CHECK (reserve_fragment (1, page + 4096) == (long) (page + 4096));
  unsigned int count = 0;
  for (; count < 300; ++count) {
    long result = reserve_fragment (1, arena + count * 12288ULL);
    if (result == -4) break;
    CHECK (result == (long) (arena + count * 12288ULL));
  }
  CHECK (count > 0 && count < 300 && close (fd) == 0);
  fd = socket (AF_INET, SOCK_STREAM, 0);
  CHECK (fd >= 0 && dial (fd, 0x0a000202, port) == -1 && errno == EAGAIN);
  CHECK (reserve_fragment (5, arena + --count * 12288ULL) == 0);
  CHECK (dial (fd, 0x0a000202, port) == 0 && close (fd) == 0);
  for (unsigned int i = 0; i < count; ++i)
    CHECK (reserve_fragment (5, arena + i * 12288ULL) == 0);
  CHECK (reserve_fragment (5, page - 4096) == 0 && reserve_fragment (5, page + 4096) == 0);
  puts ("GLIBC_NET2_DEFERRED_RELEASE_RECOVERED");
}
static void exercise_concurrent_close (unsigned int port)
{
  int fd = socket (AF_INET, SOCK_STREAM, 0);
  CHECK (fd >= 0 && dial (fd, 0x0a000202, port) == 0);
  int file = open ("/tmp/p1h_unrelated", O_CREAT | O_RDWR | O_TRUNC, 0600);
  CHECK (file >= 0 && write (file, "safe", 4) == 4);
  struct poll_worker_context context = { .fd = fd };
  pthread_t worker;
  CHECK (pthread_create (&worker, NULL, poll_worker, &context) == 0);
  uint64_t limit = clock_ns () + 500000000ULL;
  int observed = 0;
  while (clock_ns () < limit && !__atomic_load_n (&context.done, __ATOMIC_ACQUIRE)) {
    if (__atomic_load_n (&context.entered, __ATOMIC_ACQUIRE)) {
      struct { uint32_t version, size, kind, reserved; uint64_t target, pid, generation, deadline; } request =
        { 1, 48, 1, 0, 0, 0, 0, clock_ns () + 100000000ULL };
      struct { uint32_t version, size, kind, flags; uint64_t observed, completed, pid, parent, generation, object, ticks;
        uint32_t state, threads, blocked, pages, limit, channels, channel_limit, names, name_limit, pipes, pipe_limit, reserved; } snapshot;
      CHECK (sizeof (snapshot) == 120 && native_trap (90, (uint64_t) &request, (uint64_t) &snapshot) == 0);
      if (snapshot.threads == 2 && snapshot.blocked == 1 && !__atomic_load_n (&context.done, __ATOMIC_ACQUIRE)) {
        observed = 1; printf ("GLIBC_NET2_POLL_PENDING threads=2 blocked=1\n"); break;
      }
    }
    sched_yield ();
  }
  CHECK (observed);
  CHECK (close (fd) == 0);
  int replacement = socket (AF_INET, SOCK_STREAM, 0);
  CHECK (replacement == fd);
  char text[4];
  CHECK (lseek (file, 0, SEEK_SET) == 0 && read (file, text, 4) == 4 && !memcmp (text, "safe", 4));
  CHECK (pthread_join (worker, NULL) == 0);
  printf ("GLIBC_NET2_CLOSE_RESULT result=%d error=%d revents=%d elapsed_ns=%llu\n",
          context.result, context.error, context.revents, (unsigned long long) context.elapsed);
  CHECK (context.result == 1 && context.revents == POLLNVAL && context.elapsed < 2000000000ULL);
  CHECK (send (replacement, text, 1, 0) == -1 && errno == ENOTCONN);
  CHECK (close (replacement) == 0 && close (file) == 0);
  printf ("GLIBC_NET2_CLOSE_IDENTITY elapsed_ns=%llu revents=%d\n", (unsigned long long) context.elapsed, context.revents);
}

int
main (int argc, char **argv)
{
  CHECK (argc >= 3);
  unsigned long port = strtoul (argv[2], NULL, 10);
  CHECK (port > 0 && port <= 65535);
  if (!strcmp (argv[1], "stream") || !strcmp (argv[1], "legacy_wait"))
    {
      CHECK (argc == 4);
      exercise_stream (port, argv[3], !strcmp (argv[1], "legacy_wait"));
    }
  else if (!strcmp (argv[1], "half_close"))
    {
      CHECK (argc == 4);
      exercise_half_close (port, argv[3]);
    }
  else if (!strcmp (argv[1], "stall"))
    {
      CHECK (argc == 4);
      exercise_stalled_peer (argv[3]);
    }
  else if (!strcmp (argv[1], "nonblocking")) { CHECK (argc == 4); exercise_nonblocking (port, argv[3], 0); }
  else if (!strcmp (argv[1], "nonblocking_refused")) exercise_nonblocking (port, "", 1);
  else if (!strcmp (argv[1], "read_close")) { CHECK (argc == 4); exercise_read_close (port, argv[3]); }
  else if (!strcmp (argv[1], "window")) { CHECK (argc == 4); exercise_window (port, argv[3]); }
  else if (!strcmp (argv[1], "concurrent_close")) exercise_concurrent_close (port);
  else if (!strcmp (argv[1], "deferred_release")) exercise_deferred_release (port);
  else if (!strcmp (argv[1], "pipe_poll")) exercise_pipe_poll ();
  else if (!strcmp (argv[1], "capacity")) exercise_capacity ();
  else
    {
      CHECK (socket (AF_INET6, SOCK_STREAM, 0) == -1 && errno == EAFNOSUPPORT);
      CHECK (socket (AF_INET, SOCK_DGRAM, 0) == -1 && errno == EOPNOTSUPP);
      int nonblocking = socket (AF_INET, SOCK_STREAM | SOCK_NONBLOCK, 0);
      CHECK (nonblocking >= 0 && (fcntl (nonblocking, F_GETFL) & O_NONBLOCK));
      CHECK (close (nonblocking) == 0);
      CHECK (dial (-1, 0x0a000202, port) == -1 && errno == EBADF);
      CHECK (send (1, "x", 1, 0) == -1 && errno == ENOTSOCK);
      int fd = socket (AF_INET, SOCK_STREAM, 0);
      CHECK (fd >= 0);
      unsigned int address = 0x0a000202;
      int expected = ENETDOWN;
      if (!strcmp (argv[1], "wrong_pid"))
        {
          CHECK (setenv ("XOS_NET_SERVICE_PID", "1", 1) == 0);
          expected = EACCES;
        }
      else if (!strcmp (argv[1], "denied")) { address = 0xc0000201; expected = EACCES; }
      else if (!strcmp (argv[1], "refused")) expected = ECONNREFUSED;
      else CHECK (!strcmp (argv[1], "no_service"));
      CHECK (dial (fd, address, port) == -1 && errno == expected);
      CHECK (close (fd) == 0);
    }
  printf ("GLIBC_NET2_PASS %s\n", argv[1]);
  return 0;
}
