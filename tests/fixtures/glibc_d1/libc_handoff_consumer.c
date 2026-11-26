/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <unistd.h>

/* This object is linked independently against the component's versioned
   exported functions. The native observer calls only its ELF entry. */
int
d1_consumer_read_close (int fd, const char *expected, size_t length)
{
  char data[4];
  if (length == 0 || length > sizeof (data))
    return -EINVAL;
  const ssize_t count = read (fd, data, length);
  if (count < 0)
    return -errno;
  if ((size_t) count != length)
    return -EIO;
  for (size_t i = 0; i < length; ++i)
    if (data[i] != expected[i])
      return -EILSEQ;
  return close (fd) == 0 ? 0 : -errno;
}
