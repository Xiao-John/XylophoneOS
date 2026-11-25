/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <errno.h>
#include <stddef.h>
#include <sys/random.h>
static long raw;
static size_t count;
static int calls;
long __xos_random_test_trap (void *buffer, size_t length)
{ (void) buffer; ++calls; count = length; return raw; }
int main (void)
{
  unsigned char bytes[300];
  errno = 7; raw = 0;
  assert (__getrandom (bytes, 300, 0) == 256 && count == 256 && errno == 7);
  assert (__getrandom (0, 0, 0) == 0 && count == 0);
  int before = calls;
  assert (__getrandom (bytes, 1, GRND_RANDOM) == -1 && errno == ENOTSUP && calls == before);
  assert (__getrandom (bytes, 1, 0x80) == -1 && errno == EINVAL && calls == before);
  raw = -14; assert (__getrandom (bytes, 1, 0) == -1 && errno == EFAULT);
  raw = -22; assert (__getrandom (bytes, 1, 0) == -1 && errno == EINVAL);
  raw = -38; assert (__getrandom (bytes, 1, 0) == -1 && errno == ENOSYS);
  raw = -5; assert (__getrandom (bytes, 1, 0) == -1 && errno == EIO);
  before = calls; assert (getentropy (bytes, 257) == -1 && errno == EIO && calls == before);
  raw = 0; assert (getentropy (bytes, 256) == 0 && count == 256);
  raw = -5; assert (getentropy (bytes, 1) == -1 && errno == EIO);
}
