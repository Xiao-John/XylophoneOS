/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <pthread.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <time.h>
#include "xos_thread_extensions.h"
int __pthread_tryjoin_np(pthread_t, void **);
int __pthread_getcpuclockid(pthread_t, clockid_t *);
int __pthread_clockjoin_ex(pthread_t, void **, clockid_t, const struct timespec *, bool);
int __clock_gettime(clockid_t, struct timespec *);
int __clock_getres(clockid_t, struct timespec *);
static long response;
static unsigned long seen_tid, seen_mode, seen_deadline, calls, legacy_calls;
static unsigned long user = 27, system_time = 31;
static int skew_case, sample_index, join_index;
static unsigned long join_deadlines[4];
void __pthread_testcancel(void) {}
long __xos_clock_test_trap(unsigned long number, unsigned long first) {
  (void) first;
  assert(number == 46 || number == 64);
  if (skew_case == 1) {
    int first_sample = sample_index++ == 0;
    return number == 46 ? (first_sample ? 100000000000L : 102000000000L)
                       : (first_sample ? 10000000000L : 12000000000L);
  }
  if (skew_case == 2 || skew_case == 3) {
    int pair = sample_index++ / 2;
    if (pair == 0) return number == 46 ? 100000000000L : 10400000000L;
    return number == 46 ? (skew_case == 2 ? 100600000000L : 101000000000L)
                       : (skew_case == 2 ? 10600000000L : 11000000000L);
  }
  return number == 46 ? 1000 : 1000000000;
}
long __xos_thread_identity_test_call(unsigned long number, unsigned long first, unsigned long second) {
  assert(number == 44 && first == 7);
  ++legacy_calls;
  if (!response) *(unsigned long *)second = 0x125;
  return response;
}
long __xos_thread_extensions_test_call(unsigned long number, unsigned long first,
                                     unsigned long second, unsigned long third) {
  if (number == 46 || number == 64) return __xos_clock_test_trap(number, first);
  ++calls;
  if (number == 44) {
    struct xos_join_options *options = (void *)third;
    assert(options->version == 1 && options->size == 32 && !options->reserved);
    seen_tid = first; seen_mode = options->mode; seen_deadline = options->deadline_ns;
    if (skew_case) {
      assert(join_index < 4);
      join_deadlines[join_index++] = seen_deadline;
      long status = skew_case == 2 && join_index == 2 ? 0 : -13;
      if (!status) *(unsigned long *)second = 0x125;
      return status;
    }
    if (!response) *(unsigned long *)second = 0x125;
  } else {
    assert(number == 41 && second == 1 && third == 0);
    struct xos_thread_cpu_sample *sample = (void *)first;
    assert(sample->version == 1 && sample->size == 56 && !sample->reserved);
    seen_tid = sample->tid;
    if (!response) { sample->user_ns = user; sample->system_ns = system_time; sample->resolution_ns = 9; }
  }
  return response;
}
int main(void) {
  void *value = (void *)0x888;
  response = -12;
  errno = EDOM;
  assert(__pthread_tryjoin_np(7, &value) == EBUSY && value == (void *)0x888 && errno == EDOM);
  assert(seen_mode == 1 && seen_deadline == 0 && seen_tid == 7);
  response = 0;
  assert(__pthread_tryjoin_np(7, &value) == 0 && value == (void *)0x125);
  assert(__pthread_clockjoin_ex(7, NULL, CLOCK_REALTIME, NULL, true) == 0 && legacy_calls == 1);
  struct timespec limit = {2, 3};
  response = 0; value = (void *)0x888;
  assert(__pthread_clockjoin_ex(7, &value, CLOCK_REALTIME, &limit, true) == 0 && value == (void *)0x125);
  assert(seen_mode == 2 && seen_deadline == 1000001003UL);
  response = -13;
  assert(__pthread_clockjoin_ex(7, NULL, CLOCK_MONOTONIC, &limit, true) == ETIMEDOUT && seen_deadline == 2000000003UL);
  limit = (struct timespec){-1, 0};
  assert(__pthread_clockjoin_ex(7, NULL, CLOCK_REALTIME, &limit, true) == ETIMEDOUT && seen_deadline == 0);
  limit = (struct timespec){0, 1000000000};
  unsigned long before = calls;
  assert(__pthread_clockjoin_ex(7, NULL, CLOCK_REALTIME, &limit, true) == EINVAL && calls == before);
  limit = (struct timespec){LONG_MAX, 0};
  assert(__pthread_clockjoin_ex(7, NULL, CLOCK_REALTIME, &limit, true) == EOVERFLOW && calls == before);
  limit = (struct timespec){0, 0};
  assert(__pthread_clockjoin_ex(7, NULL, -1, &limit, true) == EINVAL && calls == before);

  limit = (struct timespec){11, 0};
  skew_case = 1; sample_index = join_index = 0; value = (void *)0x888;
  assert(__pthread_clockjoin_ex(7, &value, CLOCK_REALTIME, &limit, true) == ETIMEDOUT);
  assert(join_index == 1 && join_deadlines[0] == 0 && value == (void *)0x888);
  skew_case = 2; sample_index = join_index = 0;
  assert(__pthread_clockjoin_ex(7, &value, CLOCK_REALTIME, &limit, true) == 0 && value == (void *)0x125);
  assert(join_index == 2 && join_deadlines[0] == 100600000000UL && join_deadlines[1] == 101000000000UL);
  skew_case = 3; sample_index = join_index = 0; value = (void *)0x888;
  assert(__pthread_clockjoin_ex(7, &value, CLOCK_REALTIME, &limit, true) == ETIMEDOUT);
  assert(join_index == 2 && join_deadlines[0] == 100600000000UL && join_deadlines[1] == 0 && value == (void *)0x888);
  skew_case = 0; response = -2; before = calls;
  assert(__pthread_clockjoin_ex(7, &value, CLOCK_REALTIME, &limit, true) == EINVAL && calls == before + 1);

  clockid_t clock = 123;
  response = -15;
  assert(__pthread_getcpuclockid(7, &clock) == ESRCH && clock == 123);
  response = -2;
  assert(__pthread_getcpuclockid(7, &clock) == ENOTSUP && clock == 123);
  response = -19;
  assert(__pthread_getcpuclockid(7, &clock) == ENOTSUP && clock == 123);
  before = calls;
  assert(__pthread_getcpuclockid(0, &clock) == ESRCH && calls == before);
  assert(__pthread_getcpuclockid(ULONG_MAX, &clock) == EOVERFLOW && calls == before);
  assert(__pthread_getcpuclockid(7, NULL) == EINVAL && calls == before);
  response = 0;
  assert(__pthread_getcpuclockid(INT_MAX - 1UL, &clock) == 0 && clock == -INT_MAX);
  struct timespec time = {0, 0};
  assert(__clock_gettime(clock, &time) == 0 && seen_tid == INT_MAX - 1UL && time.tv_nsec == 58);
  assert(__clock_getres(clock, &time) == 0 && time.tv_sec == 0 && time.tv_nsec == 9);
  assert(__clock_getres(clock, NULL) == 0);
  response = -15;
  time = (struct timespec){123, 456};
  assert(__clock_gettime(clock, &time) == -1 && errno == ESRCH && time.tv_sec == 123 && time.tv_nsec == 456);
  response = 0; user = ULONG_MAX;
  assert(__clock_gettime(clock, &time) == -1 && errno == EOVERFLOW && time.tv_sec == 123);
  before = calls;
  assert(__clock_gettime(INT_MIN, &time) == -1 && errno == EINVAL && calls == before);
  assert(__clock_gettime(-1, &time) == -1 && errno == EINVAL && calls == before);
  puts("THREAD_JOIN_CLOCK_HOST_PASS");
}
