// SPDX-License-Identifier: Apache-2.0
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <poll.h>
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
  CHECK (fcntl (fd, F_SETFL, O_RDWR | O_NONBLOCK) == -1 && errno == ENOTSUP);
  CHECK (dial (fd, 0x0a000202, port) == 0);
  CHECK (dial (fd, 0x0a000202, port) == -1 && errno == EISCONN);
  if (legacy)
    {
      struct pollfd pending = { .fd = fd, .events = POLLOUT };
      CHECK (poll (&pending, 1, 40) == -1 && errno == EOPNOTSUPP);
      CHECK (shutdown (fd, SHUT_WR) == -1 && errno == EOPNOTSUPP);
    }
  CHECK (send (fd, nonce, 32, MSG_DONTWAIT) == -1 && errno == EOPNOTSUPP);
  CHECK (shutdown (fd, SHUT_RD) == -1 && errno == EOPNOTSUPP);
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
  CHECK (poll (&pending, 1, 0) == -1 && errno == EOPNOTSUPP);
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
  CHECK (poll (&pending, 1, 40) == 0 && !pending.revents);
  CHECK (clock_gettime (CLOCK_MONOTONIC, &after) == 0);
  long elapsed = (after.tv_sec - before.tv_sec) * 1000000000L + after.tv_nsec - before.tv_nsec;
  CHECK (elapsed >= 40000000L && elapsed < 700000000L);
  printf ("GLIBC_NET2_POLL_TIMEOUT elapsed_ns=%ld\n", elapsed);
  CHECK (poll (&pending, 1, 2500) == 1 && pending.revents == POLLOUT);
  CHECK (close (fd) == 0);
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
  else if (!strcmp (argv[1], "capacity")) exercise_capacity ();
  else
    {
      CHECK (socket (AF_INET6, SOCK_STREAM, 0) == -1 && errno == EAFNOSUPPORT);
      CHECK (socket (AF_INET, SOCK_DGRAM, 0) == -1 && errno == EOPNOTSUPP);
      CHECK (socket (AF_INET, SOCK_STREAM | SOCK_NONBLOCK, 0) == -1 && errno == EOPNOTSUPP);
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
