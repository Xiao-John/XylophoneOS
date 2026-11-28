/* SPDX-License-Identifier: Apache-2.0 */
#define _GNU_SOURCE 1
#include <errno.h>
#include <limits.h>
#include <pthread.h>
#include <semaphore.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define REQUIRE(condition) do { if (!(condition)) { \
  printf("ISSUE125_FAIL line=%d errno=%d\n", __LINE__, errno); exit(1); \
} } while (0)
static sem_t started, work, complete, finish;
static pthread_t target;
static unsigned long worker_cpu;
static long trap(unsigned long, unsigned long, unsigned long, unsigned long);

static unsigned long ns(clockid_t clock) {
  struct timespec t;
  REQUIRE(clock_gettime(clock, &t) == 0);
  return (unsigned long)t.tv_sec * 1000000000UL + t.tv_nsec;
}
static struct timespec after(clockid_t clock, unsigned long delta) {
  unsigned long total = ns(clock) + delta;
  return (struct timespec){total / 1000000000UL, total % 1000000000UL};
}
static void pause_ns(unsigned long delta) {
  /* A test scheduling aid using the already supported native wait. This
     fixture does not add or claim a POSIX nanosleep implementation. */
  REQUIRE(trap(47, ns(CLOCK_MONOTONIC) + delta, 0, 0) == 0);
}
static void burn(unsigned long delta) {
  unsigned long end = ns(CLOCK_MONOTONIC) + delta;
  volatile unsigned long accumulator = 0;
  while (ns(CLOCK_MONOTONIC) < end)
    for (unsigned int i = 0; i != 20000; ++i) accumulator += i;
}
static void *worker(void *argument) {
  (void)argument;
  REQUIRE(sem_post(&started) == 0);
  REQUIRE(sem_wait(&work) == 0);
  burn(50000000);
  worker_cpu = ns(CLOCK_THREAD_CPUTIME_ID);
  REQUIRE(sem_post(&complete) == 0);
  REQUIRE(sem_wait(&finish) == 0);
  return (void *)0x125;
}
static void *contending_joiner(void *argument) {
  (void)argument;
  struct timespec limit = after(CLOCK_REALTIME, 100000000);
  REQUIRE(sem_post(&started) == 0);
  void *value = (void *)0x888;
  int result = pthread_timedjoin_np(target, &value, &limit);
  REQUIRE(result == ETIMEDOUT && value == (void *)0x888);
  return (void *)0x126;
}
static long trap(unsigned long n, unsigned long a, unsigned long b, unsigned long c) {
  long result;
  __asm__ volatile("int $0x80" : "=a"(result) : "a"(n), "D"(a), "S"(b), "d"(c) : "memory", "cc");
  return result;
}
static void boundary_requests(void) {
  struct { unsigned int version, size; unsigned long reserved, tid, user, system, elapsed, resolution; }
    sample = {1, 56, 0, (unsigned long)pthread_self(), 11, 12, 13, 14};
  REQUIRE(sizeof sample == 56);
  sample.version = 2;
  REQUIRE(trap(41, (unsigned long)&sample, 1, 0) == -2 && sample.user == 11);
  sample.version = 1; sample.reserved = 1;
  REQUIRE(trap(41, (unsigned long)&sample, 1, 0) == -2 && sample.user == 11);
  sample.reserved = 0;
  REQUIRE(trap(41, (unsigned long)&sample, 2, 0) == -2 && sample.user == 11);
  REQUIRE(trap(41, (unsigned long)&sample, 1, 1) == -2 && sample.user == 11);
  sample.tid = ULONG_MAX;
  REQUIRE(trap(41, (unsigned long)&sample, 1, 0) == -15 && sample.user == 11);
  REQUIRE(trap(41, 1, 1, 0) == -11);
  struct { unsigned int version, size; unsigned long reserved, deadline, mode; }
    options = {1, 32, 0, 0, 1};
  unsigned long value = 0x888;
  options.version = 2;
  REQUIRE(trap(44, (unsigned long)target, (unsigned long)&value, (unsigned long)&options) == -2 && value == 0x888);
  options.version = 1; options.mode = 3;
  REQUIRE(trap(44, (unsigned long)target, (unsigned long)&value, (unsigned long)&options) == -2 && value == 0x888);
  options.mode = 1; options.deadline = 1;
  REQUIRE(trap(44, (unsigned long)target, (unsigned long)&value, (unsigned long)&options) == -2 && value == 0x888);
  options.deadline = 0; options.reserved = 1;
  REQUIRE(trap(44, (unsigned long)target, (unsigned long)&value, (unsigned long)&options) == -2 && value == 0x888);
  REQUIRE(trap(44, (unsigned long)target, (unsigned long)&value, 1) == -11 && value == 0x888);
  puts("ISSUE125_PASS versioned_abi_invalid_requests");
}
#ifndef XOS_THREADED_RUNTIME
static void cross_process_clock(void) {
  clockid_t main_clock;
  struct timespec resolution;
  REQUIRE(pthread_getcpuclockid(pthread_self(), &main_clock) == 0);
  pid_t child = fork();
  REQUIRE(child >= 0);
  if (child == 0) {
    errno = 0;
    REQUIRE(clock_gettime(main_clock, &resolution) == -1 && errno == ESRCH);
    puts("ISSUE125_PASS cross_process_cpu_query_rejected");
    REQUIRE(fflush(stdout) == 0);
    _exit(0);
  }
  int child_status;
  REQUIRE(waitpid(child, &child_status, 0) == child && WIFEXITED(child_status) && WEXITSTATUS(child_status) == 0);
}
#endif
int main(int argc, char **argv) {
  /* Stock fork is supported before entering the multithreaded profile. */
#ifndef XOS_THREADED_RUNTIME
  if (argc == 1) cross_process_clock();
#endif
  REQUIRE(sem_init(&started, 0, 0) == 0 && sem_init(&work, 0, 0) == 0);
  REQUIRE(sem_init(&complete, 0, 0) == 0 && sem_init(&finish, 0, 0) == 0);
  REQUIRE(pthread_create(&target, NULL, worker, NULL) == 0);
  REQUIRE(sem_wait(&started) == 0);
  void *value = (void *)0x888;
  clockid_t target_clock = 123;
  if (argc > 1 && strcmp(argv[1], "old-kernel") == 0) {
    unsigned long before = ns(CLOCK_MONOTONIC);
    REQUIRE(pthread_tryjoin_np(target, &value) == EINVAL && value == (void *)0x888);
    struct timespec limit = after(CLOCK_REALTIME, 30000000);
    REQUIRE(pthread_timedjoin_np(target, &value, &limit) == EINVAL && value == (void *)0x888);
    REQUIRE(pthread_getcpuclockid(target, &target_clock) == ENOTSUP && target_clock == 123);
    REQUIRE(ns(CLOCK_MONOTONIC) - before < 1000000000UL);
    REQUIRE(sem_post(&work) == 0 && sem_post(&finish) == 0);
    REQUIRE(pthread_join(target, &value) == 0 && value == (void *)0x125);
    puts("ISSUE125_PASS old_kernel_explicit_rejection_legacy_join");
    return 0;
  }
  errno = EDOM;
  unsigned long before = ns(CLOCK_MONOTONIC);
  REQUIRE(pthread_tryjoin_np(target, &value) == EBUSY && value == (void *)0x888 && errno == EDOM);
  REQUIRE(ns(CLOCK_MONOTONIC) - before < 1000000000UL);
  struct timespec limit = after(CLOCK_REALTIME, 30000000);
  before = ns(CLOCK_MONOTONIC);
  REQUIRE(pthread_timedjoin_np(target, &value, &limit) == ETIMEDOUT && value == (void *)0x888);
  REQUIRE(ns(CLOCK_MONOTONIC) - before >= 20000000);
  struct timespec past = {-1, 0}, invalid = {0, 1000000000};
  REQUIRE(pthread_timedjoin_np(target, &value, &past) == ETIMEDOUT);
  REQUIRE(pthread_timedjoin_np(target, &value, &invalid) == EINVAL);
  REQUIRE(pthread_tryjoin_np(pthread_self(), NULL) == EDEADLK);
  REQUIRE(pthread_tryjoin_np((pthread_t)0, NULL) == ESRCH);
  puts("ISSUE125_PASS tryjoin_deadline_timeout_output_preserved");

  REQUIRE(pthread_getcpuclockid(target, &target_clock) == 0 && target_clock < -1);
  clockid_t main_clock;
  REQUIRE(pthread_getcpuclockid(pthread_self(), &main_clock) == 0 && main_clock != target_clock);
  struct timespec resolution;
  REQUIRE(clock_getres(target_clock, &resolution) == 0 && (resolution.tv_sec || resolution.tv_nsec));
  /* The timed join above blocked this caller for 30 ms while the worker
     reached sem_wait(work). Nothing releases that semaphore before sampling. */
  unsigned long target_before = ns(target_clock), main_before = ns(main_clock);
  burn(50000000);
  REQUIRE(ns(target_clock) == target_before);
  REQUIRE(ns(main_clock) > main_before);
  REQUIRE(sem_post(&work) == 0 && sem_wait(&complete) == 0);
  REQUIRE(ns(target_clock) > target_before && ns(target_clock) >= worker_cpu);
  REQUIRE(pthread_getcpuclockid((pthread_t)ULONG_MAX, &main_clock) == EOVERFLOW);
  REQUIRE(pthread_getcpuclockid((pthread_t)0, &main_clock) == ESRCH);
  REQUIRE(pthread_getcpuclockid(target, NULL) == EINVAL);
  puts("ISSUE125_PASS target_cpu_identity_sleep_busy_resolution");
  boundary_requests();

  pthread_t joiner;
  REQUIRE(pthread_create(&joiner, NULL, contending_joiner, NULL) == 0);
  REQUIRE(sem_wait(&started) == 0);
  pause_ns(20000000);
  REQUIRE(pthread_tryjoin_np(target, &value) == EINVAL);
  REQUIRE(pthread_detach(target) == EINVAL);
  REQUIRE(pthread_join(joiner, &value) == 0 && value == (void *)0x126);
  REQUIRE(sem_post(&finish) == 0);
#ifndef XOS_THREADED_RUNTIME
  limit = after(CLOCK_MONOTONIC, 2000000000UL);
  REQUIRE(pthread_clockjoin_np(target, &value, CLOCK_MONOTONIC, &limit) == 0 && value == (void *)0x125);
#else
  limit = after(CLOCK_REALTIME, 2000000000UL);
  REQUIRE(pthread_timedjoin_np(target, &value, &limit) == 0 && value == (void *)0x125);
#endif
  REQUIRE(pthread_tryjoin_np(target, NULL) == ESRCH);
  errno = 0;
  REQUIRE(clock_gettime(target_clock, &resolution) == -1 && errno == ESRCH);
  REQUIRE(pthread_getcpuclockid(target, &main_clock) == ESRCH);
  puts("ISSUE125_PASS join_detach_contention_timeout_release_stale_clock");

  /* Reuse the kernel's bounded thread slots; a stale clock must not alias. */
  for (int round = 0; round < 8; ++round) {
    REQUIRE(pthread_create(&target, NULL, worker, NULL) == 0);
    REQUIRE(sem_wait(&started) == 0);
    REQUIRE(sem_post(&work) == 0 && sem_wait(&complete) == 0);
    clockid_t exiting_clock;
    REQUIRE(pthread_getcpuclockid(target, &exiting_clock) == 0);
    REQUIRE(sem_post(&finish) == 0);
    pause_ns(20000000);
    errno = 0;
    REQUIRE(clock_getres(exiting_clock, NULL) == -1 && errno == ESRCH);
    REQUIRE(pthread_tryjoin_np(target, &value) == 0 && value == (void *)0x125);
    errno = 0;
    REQUIRE(clock_getres(target_clock, NULL) == -1 && errno == ESRCH);
  }
  REQUIRE(pthread_create(&target, NULL, worker, NULL) == 0);
  REQUIRE(sem_wait(&started) == 0);
  clockid_t detached_clock;
  REQUIRE(pthread_getcpuclockid(target, &detached_clock) == 0);
  REQUIRE(pthread_detach(target) == 0);
  REQUIRE(pthread_tryjoin_np(target, NULL) == EINVAL);
  REQUIRE(sem_post(&work) == 0 && sem_wait(&complete) == 0);
  REQUIRE(ns(detached_clock) >= worker_cpu);
  REQUIRE(sem_post(&finish) == 0);
  pause_ns(20000000);
  errno = 0;
  REQUIRE(clock_getres(detached_clock, NULL) == -1 && errno == ESRCH);
  REQUIRE(pthread_tryjoin_np(target, NULL) == ESRCH);
  puts("ISSUE125_PASS detached_cpu_clock_lifecycle");
  puts("ISSUE125_PASS lifecycle_reuse_and_complete");
  return 0;
}
