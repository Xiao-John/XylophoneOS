/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <time.h>
#include <xos_cpu_time.h>
#include <stdint.h>
static unsigned long last_number, last_first;
static long next_result;
static struct xos_cpu_time sample;
long __xos_clock_test_trap (unsigned long number, unsigned long first)
{
  last_number = number; last_first = first;
  if (number == 89) {
    struct xos_cpu_time *output = (void *) first;
    assert (output->version == 1 && output->size == sizeof (*output));
    if (next_result == 0) *output = sample;
  }
  return next_result;
}
int __clock_gettime (clockid_t, struct timespec *);
int __clock_getres (clockid_t, struct timespec *);
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
  next_result = 0;
  sample.user_ns = 1500000000ULL; sample.system_ns = 200000000ULL;
  sample.thread_user_ns = 300000000ULL; sample.thread_system_ns = 42;
  assert (__clock_gettime (CLOCK_PROCESS_CPUTIME_ID, &value) == 0 && last_number == 89);
  assert (value.tv_sec == 1 && value.tv_nsec == 700000000);
  assert (__clock_gettime (CLOCK_THREAD_CPUTIME_ID, &value) == 0);
  assert (value.tv_sec == 0 && value.tv_nsec == 300000042);
  value.tv_sec = 11; value.tv_nsec = 22;
  sample.user_ns = UINT64_MAX; sample.system_ns = 1;
  assert (__clock_gettime (CLOCK_PROCESS_CPUTIME_ID, &value) == -1 && errno == EOVERFLOW);
  assert (value.tv_sec == 11 && value.tv_nsec == 22);
  next_result = -19; assert (__clock_gettime (CLOCK_PROCESS_CPUTIME_ID, &value) == -1 && errno == ENOTSUP);
  next_result = -5; assert (__clock_gettime (CLOCK_THREAD_CPUTIME_ID, &value) == -1 && errno == ENOMEM);
  next_result = -2; assert (__clock_gettime (CLOCK_THREAD_CPUTIME_ID, &value) == -1 && errno == EIO);
  last_number = 0;
  assert (__clock_gettime (987, &value) == -1 && errno == EINVAL && last_number == 0);
  assert (value.tv_sec == 11 && value.tv_nsec == 22);
  next_result = 10000000; errno = 7;
  assert (__clock_getres (CLOCK_MONOTONIC, &value) == 0 && last_number == 46 && last_first == 1);
  assert (value.tv_sec == 0 && value.tv_nsec == 10000000 && errno == 7);
  assert (__clock_getres (CLOCK_REALTIME, 0) == 0 && last_number == 46 && last_first == 1);
  next_result = 0; sample.resolution_ns = 1500000001ULL;
  assert (__clock_getres (CLOCK_PROCESS_CPUTIME_ID, &value) == 0 && last_number == 89);
  assert (value.tv_sec == 1 && value.tv_nsec == 500000001);
  assert (__clock_getres (CLOCK_THREAD_CPUTIME_ID, 0) == 0);
  value.tv_sec = 11; value.tv_nsec = 22; next_result = -19;
  assert (__clock_getres (CLOCK_PROCESS_CPUTIME_ID, &value) == -1 && errno == ENOTSUP);
  next_result = -5; assert (__clock_getres (CLOCK_THREAD_CPUTIME_ID, &value) == -1 && errno == ENOMEM);
  next_result = 0; sample.resolution_ns = 0;
  assert (__clock_getres (CLOCK_THREAD_CPUTIME_ID, &value) == -1 && errno == EIO);
  assert (__clock_getres (CLOCK_MONOTONIC, &value) == -1 && errno == EIO);
  last_number = 0;
  assert (__clock_getres (987, &value) == -1 && errno == EINVAL && last_number == 0);
  assert (value.tv_sec == 11 && value.tv_nsec == 22);
}
