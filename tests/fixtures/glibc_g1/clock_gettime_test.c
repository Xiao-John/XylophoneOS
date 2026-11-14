/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <time.h>
static unsigned long last_number;
static long next_result;
long __xos_clock_test_trap (unsigned long number)
{ last_number = number; return next_result; }
int __clock_gettime (clockid_t, struct timespec *);
int main (void)
{
  struct timespec value = {11, 22};
  next_result = 12345678901L; errno = 7;
  assert (__clock_gettime (CLOCK_MONOTONIC, &value) == 0);
  assert (last_number == 46 && value.tv_sec == 12 && value.tv_nsec == 345678901 && errno == 7);
  next_result = LONG_MAX;
  assert (__clock_gettime (CLOCK_REALTIME, &value) == 0 && last_number == 64);
  assert (value.tv_sec == LONG_MAX / 1000000000L && value.tv_nsec == LONG_MAX % 1000000000L);
  value.tv_sec = 11; value.tv_nsec = 22; next_result = -5;
  assert (__clock_gettime (CLOCK_REALTIME, &value) == -1 && errno == EIO);
  assert (value.tv_sec == 11 && value.tv_nsec == 22);
  assert (__clock_gettime (CLOCK_MONOTONIC, &value) == -1 && errno == EOVERFLOW);
  last_number = 0;
  assert (__clock_gettime (987, &value) == -1 && errno == EINVAL && last_number == 0);
  assert (value.tv_sec == 11 && value.tv_nsec == 22);
}
