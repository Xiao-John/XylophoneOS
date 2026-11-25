/* SPDX-License-Identifier: Apache-2.0
   Standalone XOS guest test of the private native bridge.  No libc is linked. */
#include "xos_thread_create.h"
#include "xos_thread_entry.h"
#ifdef XOS_GLIBC_TEST_EXIT
# include "xos_thread_exit.h"
# define G1_JOIN_RESULT 0xfedcba9876543210UL
#else
# define G1_JOIN_RESULT 0x1234UL
#endif
#ifdef XOS_GLIBC_TEST_CLOCK
#include "xos_cpu_time.h"
#endif
#ifdef XOS_GLIBC_TEST_MEMORY
# define _SYS_MMAN_H 1
# include "bits/mman.h"
# define MAP_FAILED ((void *) -1)
extern void *_dl_early_allocate (unsigned long);
extern int __brk (void *);
extern void *__curbrk;
extern void *__mmap64 (void *, unsigned long, int, int, int, long);
extern int __mprotect (void *, unsigned long, int);
extern int __munmap (void *, unsigned long);
#endif
#if defined XOS_GLIBC_TEST_MEMORY || defined XOS_GLIBC_TEST_IDENTITY
# define _ERRNO_H 1
# include "bits/errno.h"
#endif
#ifdef XOS_GLIBC_TEST_IDENTITY
struct native_thread_info
{
  struct xos_thread_header header;
  xos_u64 pid, tid, stack_begin, stack_end, thread_pointer;
};
struct native_join_time { long sec, nsec; };
extern unsigned long __pthread_self (void);
extern unsigned long thrd_current (void);
extern int ___pthread_detach (unsigned long);
extern int __pthread_clockjoin_ex (unsigned long, void **, int,
                                   const struct native_join_time *, _Bool);
#endif

static xos_u64 child_result;
static int rollback_count;
static struct xos_thread_launch_result launch;
static int invalid_start;
#if defined XOS_GLIBC_TEST_GETPID || defined XOS_GLIBC_TEST_CLOCK \
    || defined XOS_GLIBC_TEST_RANDOM || defined XOS_GLIBC_TEST_MEMORY
__thread int __libc_errno;
#endif
#ifdef XOS_GLIBC_TEST_CLOCK
struct test_timespec { long tv_sec, tv_nsec; };
extern int __clock_gettime (int, struct test_timespec *);
extern int __clock_getres (int, struct test_timespec *);
#endif
#ifdef XOS_GLIBC_TEST_RANDOM
extern long __getrandom (void *, unsigned long, unsigned int);
extern int getentropy (void *, unsigned long);
static unsigned char random_bytes[300];
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
#ifdef XOS_GLIBC_TEST_IDENTITY
static unsigned native_cancel_checks;
void __pthread_testcancel (void)
{
  /* The backend currently has no remote cancellation delivery. Verify
     which join paths request the cancellation check. */
  ++native_cancel_checks;
}

static void check_native_self (void)
{
  struct native_thread_info info;
  if (trap (41, (xos_u64) &info, 0) != 0 || info.tid == 0
      || __pthread_self () != info.tid || thrd_current () != info.tid)
    finish (64);
}
#endif
#ifdef XOS_GLIBC_TEST_EXIT
static void last_process_exit (void)
{
  finish (0);
}
#endif
#ifdef XOS_GLIBC_TEST_MEMORY
static void check_memory (void)
{
  xos_i64 initial_break = trap (29, 0, 0);
  if (initial_break <= 0) finish (50);
  void *initial = (void *) initial_break;
  volatile unsigned char *heap = _dl_early_allocate (4097);
  if (heap != initial || __curbrk != (void *) (initial_break + 4097)) finish (51);
  heap[4096] = 0x5a;
  if (heap[4096] != 0x5a || __brk (initial) != 0 || __curbrk != initial
      || trap (29, 0, 0) != initial_break) finish (52);
  __libc_errno = 0;
  if (__brk ((void *) 1) != -1 || __libc_errno != ENOMEM || __curbrk != initial)
    finish (53);
  __libc_errno = 0;
  if (_dl_early_allocate ((unsigned long) -1) != 0 || __libc_errno != 0
      || trap (29, 0, 0) != initial_break) finish (54);

  int flags = MAP_PRIVATE | MAP_ANONYMOUS;
  void *mapped = __mmap64 (0, 4097, PROT_NONE, flags, -1, 0);
  if (mapped == MAP_FAILED) finish (55);
  __libc_errno = 0;
  if (__mmap64 (mapped, 4097, PROT_NONE, flags | MAP_FIXED_NOREPLACE, -1, 0)
        != MAP_FAILED || __libc_errno != EEXIST) finish (56);
  __libc_errno = 0;
  if (__mprotect (mapped, 4097, PROT_WRITE | PROT_EXEC) != -1
      || __libc_errno != EACCES) finish (57);
  if (__mprotect (mapped, 4097, PROT_READ | PROT_WRITE) != 0) finish (58);
  volatile unsigned char *bytes = mapped;
  if (bytes[0] != 0 || bytes[4096] != 0) finish (59);
  bytes[0] = 0x35;
  bytes[4096] = 0xac;
  if (__mprotect (mapped, 4097, PROT_READ) != 0
      || bytes[0] != 0x35 || bytes[4096] != 0xac) finish (60);
  if (__munmap (mapped, 4097) != 0) finish (61);
  __libc_errno = 0;
  if (__mprotect (mapped, 4097, PROT_READ) != -1 || __libc_errno != ENOMEM)
    finish (62);
  if (__mmap64 (mapped, 4097, PROT_NONE, flags | MAP_FIXED_NOREPLACE, -1, 0)
        != mapped || __mprotect (mapped, 4097, PROT_READ) != 0
      || bytes[0] != 0 || bytes[4096] != 0 || __munmap (mapped, 4097) != 0)
    finish (63);
}
#endif
static void guest_thread_worker (void *raw)
{
  if (((xos_u64) __builtin_frame_address (0) & 15) != 0) finish (95);
#ifdef XOS_GLIBC_TEST_IDENTITY
  check_native_self ();
  if (__pthread_self () != launch.tid) finish (65);
#endif
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
#ifdef XOS_GLIBC_TEST_EXIT
  __xos_thread_finish (G1_JOIN_RESULT, 0);
#else
  if (trap (42, 0, 0) != 0)
    finish (91);
  (void) trap (43, G1_JOIN_RESULT, 0);
  finish (92);
#endif
}
static const struct xos_thread_entry_args entry_args = {
  .run = guest_thread_worker, .argument = &child_result
};
static xos_i64 setup (const struct xos_thread_reservation *r,
                      struct xos_thread_start_parameters *p, void *context)
{
  if (context != &launch || __atomic_load_n (&launch.tid, __ATOMIC_ACQUIRE) != r->tid)
    return -77;
  *(xos_u64 *) r->tls_begin = r->tls_begin;
  p->entry = invalid_start ? 0 : (xos_u64) __xos_thread_entry;
  p->argument = (xos_u64) &entry_args;
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
#ifdef XOS_GLIBC_TEST_MEMORY
  check_memory ();
#endif
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
#ifdef XOS_GLIBC_TEST_RANDOM
  if (__getrandom (random_bytes, sizeof (random_bytes), 0) != 256) return 32;
  if (getentropy (random_bytes, 256) != 0) return 33;
  __libc_errno = 0;
  if (getentropy (random_bytes, 257) != -1 || __libc_errno != 5) return 34;
  __libc_errno = 0;
  if (__getrandom (random_bytes, 1, 1) != -1 || __libc_errno != 134) return 35;
  __libc_errno = 0;
  if (__getrandom ((void *) 1, 1, 0) != -1 || __libc_errno != 14) return 36;
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
#ifdef XOS_GLIBC_TEST_IDENTITY
  check_native_self ();
  struct native_join_time deadline = { 0, 0 };
  if (__pthread_clockjoin_ex (launch.tid, 0, 1, &deadline, 1) != ENOTSUP)
    return 66;
  if (__pthread_clockjoin_ex (__pthread_self (), 0, 0, 0, 1) != EDEADLK)
    return 67;
  void *returned = 0;
  if (__pthread_clockjoin_ex (launch.tid, &returned, 0, 0, 1) != 0)
    return 68;
  value = (xos_u64) returned;
  if (__pthread_clockjoin_ex (launch.tid, 0, 0, 0, 1) != ESRCH
      || ___pthread_detach (launch.tid) != ESRCH)
    return 69;
  if (___pthread_detach (__pthread_self ()) != 0
      || ___pthread_detach (__pthread_self ()) != EINVAL)
    return 70;
  if (native_cancel_checks != 3) return 71;
#else
  if (trap (44, launch.tid, (xos_u64) &value) != 0) return 15;
#endif
  if (value != G1_JOIN_RESULT || child_result != 0xabc) return 16;
#ifdef XOS_GLIBC_TEST_EXIT
  __xos_thread_finish (0, last_process_exit);
#endif
  return 0;
}
__asm__ (".section .text.entry,\"ax\"\n.globl _start\n"
         "_start:\ncld\nxor %ebp,%ebp\nand $-16,%rsp\n"
         "call guest_main\nmov %eax,%edi\nmov $2,%eax\nint $0x80\nud2\n");
