/* SPDX-License-Identifier: Apache-2.0
   Public pthread detach operations; sys50 is a read-only resource observer. */
#define _GNU_SOURCE 1
#include <errno.h>
#include <pthread.h>
#include <sched.h>
#include <semaphore.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#define REQUIRE(expression) do { if (!(expression)) { \
  printf ("G3-T DETACH FAIL line=%d errno=%d\n", __LINE__, errno); \
  fflush (stdout); exit (1); } } while (0)

/* E13-T v1 read-only layout, matching xos/thread_abi.hpp. */
struct native_thread_stats
{
  uint32_t version, size;
  uint64_t reserved_header;
  uint32_t processes, threads, reserved, waiting, results, free_pages;
  uint32_t process_user_pages, process_kernel_stack_pages;
};
_Static_assert (sizeof (struct native_thread_stats) == 48, "sys50 ABI size");

static struct native_thread_stats
thread_stats (void)
{
  struct native_thread_stats value;
  long result;
  __asm__ volatile ("int $0x80" : "=a" (result)
                    : "a" (50UL), "D" (&value), "S" (0UL), "d" (0UL)
                    : "memory", "cc");
  REQUIRE (result == 0 && value.version == 1 && value.size == sizeof (value)
           && value.reserved_header == 0);
  return value;
}

static uint64_t
now (void)
{
  struct timespec value;
  REQUIRE (clock_gettime (CLOCK_MONOTONIC, &value) == 0);
  return (uint64_t) value.tv_sec * 1000000000ULL + (uint64_t) value.tv_nsec;
}

static sem_t gate;
static pthread_key_t key;
static unsigned destroyed;
static _Thread_local unsigned tls_value = 19;

static void
destructor (void *value)
{
  REQUIRE ((uintptr_t) value >= 1 && (uintptr_t) value <= 16);
  REQUIRE (tls_value == 19 + (uintptr_t) value);
  __atomic_add_fetch (&destroyed, 1, __ATOMIC_RELEASE);
}

static void *
worker (void *argument)
{
  REQUIRE (tls_value == 19);
  tls_value += (unsigned) (uintptr_t) argument;
  REQUIRE (pthread_setspecific (key, argument) == 0);
  REQUIRE (sem_wait (&gate) == 0);
  return argument;
}

int
main (void)
{
  puts ("G3-T BEGIN detached lifecycle");
  REQUIRE (pthread_key_create (&key, destructor) == 0);
  REQUIRE (sem_init (&gate, 0, 0) == 0);
  struct native_thread_stats baseline = thread_stats ();
  REQUIRE (baseline.threads == 1 && baseline.reserved == 0 && baseline.results == 0);
  pthread_t previous = 0;
  for (unsigned iteration = 1; iteration <= 16; ++iteration)
    {
      pthread_attr_t attribute;
      REQUIRE (pthread_attr_init (&attribute) == 0);
      if (iteration & 1)
        REQUIRE (pthread_attr_setdetachstate (&attribute, PTHREAD_CREATE_DETACHED) == 0);
      pthread_t thread;
      REQUIRE (pthread_create (&thread, &attribute, worker,
                               (void *) (uintptr_t) iteration) == 0);
      REQUIRE (pthread_attr_destroy (&attribute) == 0);
      REQUIRE (thread != previous);
      if (!(iteration & 1))
        REQUIRE (pthread_detach (thread) == 0);
      REQUIRE (pthread_getattr_np (thread, &attribute) == 0);
      int detached;
      REQUIRE (pthread_attr_getdetachstate (&attribute, &detached) == 0
               && detached == PTHREAD_CREATE_DETACHED);
      REQUIRE (pthread_attr_destroy (&attribute) == 0);
      REQUIRE (pthread_join (thread, NULL) == EINVAL);
      REQUIRE (sem_post (&gate) == 0);

      uint64_t deadline = now () + 2000000000ULL;
      struct native_thread_stats current;
      for (;;)
        {
          current = thread_stats ();
          if (current.threads == 1 && current.reserved == 0 && current.results == 0)
            break;
          REQUIRE (now () < deadline);
          REQUIRE (sched_yield () == 0);
        }
      REQUIRE (current.process_kernel_stack_pages == baseline.process_kernel_stack_pages);
      REQUIRE (__atomic_load_n (&destroyed, __ATOMIC_ACQUIRE) == iteration);
      REQUIRE (pthread_gettid_np (thread) == -1 && pthread_join (thread, NULL) == ESRCH);
      previous = thread;
    }
  REQUIRE (pthread_key_delete (key) == 0);
  REQUIRE (sem_destroy (&gate) == 0);
  puts ("G3-T PASS detached creation detach TSD slots kernel-stack recovery rounds=16");
  return 0;
}
