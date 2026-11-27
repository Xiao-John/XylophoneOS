// SPDX-License-Identifier: Apache-2.0
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
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
exercise_stream (unsigned int port, const char *nonce)
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
  CHECK (send (fd, nonce, 32, MSG_DONTWAIT) == -1 && errno == EOPNOTSUPP);
  CHECK (shutdown (fd, SHUT_WR) == -1 && errno == ENOSYS);
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
exercise_capacity (void)
{
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
  if (!strcmp (argv[1], "stream"))
    {
      CHECK (argc == 4);
      exercise_stream (port, argv[3]);
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
