/* SPDX-License-Identifier: Apache-2.0
   Standalone XOS guest test of the private native bridge.  No libc is linked. */
#include "xos_thread_create.h"
#ifdef XOS_GLIBC_TEST_CLOCK
#include "xos_cpu_time.h"
#endif

static xos_u64 child_result;
static int rollback_count;
static struct xos_thread_launch_result launch;
static int invalid_start;
#if defined XOS_GLIBC_TEST_GETPID || defined XOS_GLIBC_TEST_CLOCK
__thread int __libc_errno;
#endif
#ifdef XOS_GLIBC_TEST_CLOCK
struct test_timespec { long tv_sec, tv_nsec; };
extern int __clock_gettime (int, struct test_timespec *);
extern int __clock_getres (int, struct test_timespec *);
#endif
#ifdef XOS_GLIBC_TEST_GETPID
extern int __getpid (void);
static int expected_pid;
#endif
#ifdef XOS_GLIBC_TEST_YIELD
extern int __sched_yield (void);
static unsigned int child_waiting, child_yielded, parent_ack;
#endif
static xos_i64 trap (xos_u64 n, xos_u64 a, xos_u64 b)
{
  xos_i64 result;
  __asm__ volatile ("int $0x80" : "=a" (result)
                    : "a" (n), "D" (a), "S" (b), "d" (0L) : "memory", "cc");
  return result;
}
static void finish (xos_u64 code) __attribute__ ((noreturn));
static void finish (xos_u64 code)
{
  (void) trap (2, code, 0);
  __builtin_trap ();
}
void guest_thread_enter (void *);
void guest_thread_worker (void *raw) __attribute__ ((noreturn, used));
void guest_thread_worker (void *raw)
{
#ifdef XOS_GLIBC_TEST_GETPID
  if (__getpid () != expected_pid) finish (94);
#endif
  xos_u64 tp;
  __asm__ volatile ("mov %%fs:0,%0" : "=r" (tp));
  if (raw != &child_result || tp == 0 || *(xos_u64 *) tp != tp)
    finish (90);
#ifdef XOS_GLIBC_TEST_YIELD
  __atomic_store_n (&child_waiting, 1, __ATOMIC_RELEASE);
  do {
    if (__sched_yield () != 0) finish (93);
    __atomic_store_n (&child_yielded, 1, __ATOMIC_RELEASE);
  } while (!__atomic_load_n (&parent_ack, __ATOMIC_ACQUIRE));
#endif
  child_result = 0xabc;
  if (trap (42, 0, 0) != 0)
    finish (91);
  (void) trap (43, 0x1234, 0);
  finish (92);
}
__asm__ (".text\n.globl guest_thread_enter\n"
         "guest_thread_enter:\ncld\nxor %ebp,%ebp\nand $-16,%rsp\n"
         "call guest_thread_worker\nud2\n");
static xos_i64 setup (const struct xos_thread_reservation *r,
                      struct xos_thread_start_parameters *p, void *context)
{
  if (context != &launch || __atomic_load_n (&launch.tid, __ATOMIC_ACQUIRE) != r->tid)
    return -77;
  *(xos_u64 *) r->tls_begin = r->tls_begin;
  p->entry = invalid_start ? 0 : (xos_u64) guest_thread_enter;
  p->argument = (xos_u64) &child_result;
  p->stack = r->stack_top;
  p->thread_pointer = r->tls_begin;
  return 0;
}
static void rollback (void *context)
{
  if (context == &launch)
    ++rollback_count;
}
int guest_main (void) __attribute__ ((used));
int guest_main (void)
{
#ifdef XOS_GLIBC_TEST_GETPID
  expected_pid = (int) trap (6, 0, 0);
  if (expected_pid <= 0 || __getpid () != expected_pid) return 18;
#endif
#ifdef XOS_GLIBC_TEST_CLOCK
  struct test_timespec sample = {11, 22};
  xos_i64 before = trap (46, 0, 0);
  if (before < 0 || __clock_gettime (1, &sample) != 0) return 19;
  xos_i64 after = trap (46, 0, 0);
  if (sample.tv_sec < 0 || sample.tv_nsec < 0 || sample.tv_nsec >= 1000000000L) return 20;
  xos_u64 sample_ns = (xos_u64) sample.tv_sec * 1000000000UL + (xos_u64) sample.tv_nsec;
  if (after < 0 || sample_ns < (xos_u64) before || sample_ns > (xos_u64) after) return 21;
  sample.tv_sec = 11; sample.tv_nsec = 22; __libc_errno = 0;
  if (__clock_gettime (987, &sample) != -1 || __libc_errno != 22 ||
      sample.tv_sec != 11 || sample.tv_nsec != 22) return 22;
#endif
#ifdef XOS_GLIBC_TEST_CLOCK
  xos_i64 native_resolution = trap (46, 1, 0);
  if (native_resolution <= 0 || __clock_getres (1, &sample) != 0) return 27;
  if ((xos_u64) sample.tv_sec * 1000000000UL + (xos_u64) sample.tv_nsec != (xos_u64) native_resolution) return 28;
  if (__clock_getres (0, 0) != 0) return 29;
  struct xos_cpu_time cpu_before = {.version = 1, .size = sizeof (cpu_before)};
  xos_i64 cpu_status = trap (89, (xos_u64) &cpu_before, 0);
  for (int which = 2; which <= 3; ++which) {
    sample.tv_sec = 11; sample.tv_nsec = 22; __libc_errno = 0;
    int resolution_result = __clock_getres (which, &sample);
    if (cpu_status == -19) {
      if (resolution_result != -1 || __libc_errno != 134 || sample.tv_sec != 11 || sample.tv_nsec != 22) return 30;
    } else {
      if (cpu_status != 0 || resolution_result != 0 ||
          (xos_u64) sample.tv_sec * 1000000000UL + (xos_u64) sample.tv_nsec != cpu_before.resolution_ns) return 31;
    }
    sample.tv_sec = 11; sample.tv_nsec = 22; __libc_errno = 0;
    int result = __clock_gettime (which, &sample);
    if (cpu_status == -19) {
      if (result != -1 || __libc_errno != 134 || sample.tv_sec != 11 || sample.tv_nsec != 22) return 23;
    } else {
      if (cpu_status != 0 || result != 0 || sample.tv_sec < 0 || sample.tv_nsec < 0 || sample.tv_nsec >= 1000000000L) return 24;
      struct xos_cpu_time cpu_after = {.version = 1, .size = sizeof (cpu_after)};
      if (trap (89, (xos_u64) &cpu_after, 0) != 0) return 25;
      xos_u64 lo = which == 2 ? cpu_before.user_ns + cpu_before.system_ns : cpu_before.thread_user_ns + cpu_before.thread_system_ns;
      xos_u64 hi = which == 2 ? cpu_after.user_ns + cpu_after.system_ns : cpu_after.thread_user_ns + cpu_after.thread_system_ns;
      xos_u64 got = (xos_u64) sample.tv_sec * 1000000000UL + (xos_u64) sample.tv_nsec;
      if (got < lo || got > hi) return 26;
    }
  }
  if (cpu_status == -19) {
    static const char unavailable[] = "[g1] cpu_time=unavailable\n";
    (void) trap (1, (xos_u64) unavailable, sizeof (unavailable) - 1);
  } else {
    static const char available[] = "[g1] cpu_time=available\n";
    (void) trap (1, (xos_u64) available, sizeof (available) - 1);
  }
#endif
  struct xos_thread_header header = {1, sizeof (header), 0};
  if (trap (52, (xos_u64) &header, 0) != 0) return 10;
  invalid_start = 1;
  if (__xos_thread_launch (65536, 4096, 0, setup, rollback, &launch, &launch) == 0) return 11;
  if (launch.abort_error != 0 || launch.tid != 0 || launch.started || rollback_count != 1) return 12;
  invalid_start = 0;
  if (__xos_thread_launch (65536, 4096, 0, setup, rollback, &launch, &launch) != 0) return 13;
  if (!launch.started || !launch.tid || launch.abort_error != 0 || rollback_count != 1) return 14;
#ifdef XOS_GLIBC_TEST_YIELD
  unsigned int attempts = 0;
  if (__sched_yield () != 0) return 17;
  while (!__atomic_load_n (&child_waiting, __ATOMIC_ACQUIRE)
         || !__atomic_load_n (&child_yielded, __ATOMIC_ACQUIRE))
    if (__sched_yield () != 0 || ++attempts == 100000) return 17;
  __atomic_store_n (&parent_ack, 1, __ATOMIC_RELEASE);
#endif
  xos_u64 value = 0;
  if (trap (44, launch.tid, (xos_u64) &value) != 0) return 15;
  if (value != 0x1234 || child_result != 0xabc) return 16;
  return 0;
}
__asm__ (".section .text.entry,\"ax\"\n.globl _start\n"
         "_start:\ncld\nxor %ebp,%ebp\nand $-16,%rsp\n"
         "call guest_main\nmov %eax,%edi\nmov $2,%eax\nint $0x80\nud2\n");
