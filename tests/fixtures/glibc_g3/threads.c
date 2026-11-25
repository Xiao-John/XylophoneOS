/* SPDX-License-Identifier: Apache-2.0
   Public glibc pthread qualification probe; link only with the candidate SDK. */
#define _GNU_SOURCE 1
#include <errno.h>
#include <limits.h>
#include <pthread.h>
#include <sched.h>
#include <semaphore.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define REQUIRE(expression) do { if (!(expression)) { \
  printf ("G3-T FAIL line=%d errno=%d\n", __LINE__, errno); \
  fflush (stdout); exit (1); } } while (0)

static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t condition = PTHREAD_COND_INITIALIZER;
static pthread_rwlock_t rwlock = PTHREAD_RWLOCK_INITIALIZER;
static pthread_barrier_t barrier;
static pthread_once_t once = PTHREAD_ONCE_INIT;
static pthread_key_t key;
static sem_t gate;
static int ready, start, operations, once_calls, destroyed, cleanup_order;
static _Thread_local unsigned tls_value = 73;
static _Thread_local unsigned tls_zero;
static int shared_value;

static void
initialize_once (void)
{
  ++once_calls;
}

static void
destroy_value (void *value)
{
  REQUIRE ((uintptr_t) value >= 1 && (uintptr_t) value <= 3);
  if ((uintptr_t) value == 2)
    REQUIRE (cleanup_order == 21);
  REQUIRE (pthread_mutex_lock (&lock) == 0);
  ++destroyed;
  REQUIRE (pthread_mutex_unlock (&lock) == 0);
}

static void
cleanup_value (void *value)
{
  REQUIRE (tls_value == 1002 && tls_zero == 2);
  REQUIRE (pthread_mutex_lock (&lock) == 0);
  cleanup_order = cleanup_order * 10 + (int) (uintptr_t) value;
  REQUIRE (pthread_mutex_unlock (&lock) == 0);
}

static struct timespec
deadline_after (clockid_t clock, long nanoseconds)
{
  struct timespec value;
  REQUIRE (clock_gettime (clock, &value) == 0);
  value.tv_nsec += nanoseconds;
  if (value.tv_nsec >= 1000000000L)
    {
      ++value.tv_sec;
      value.tv_nsec -= 1000000000L;
    }
  return value;
}

static void
check_deadline_reached (clockid_t clock, struct timespec deadline)
{
  struct timespec current;
  REQUIRE (clock_gettime (clock, &current) == 0);
  REQUIRE (current.tv_sec > deadline.tv_sec
           || (current.tv_sec == deadline.tv_sec
               && current.tv_nsec >= deadline.tv_nsec));
}

static void
check_stack (pthread_t thread, int current)
{
  pthread_attr_t attribute;
  void *bottom;
  size_t size;
  REQUIRE (pthread_getattr_np (thread, &attribute) == 0);
  REQUIRE (pthread_attr_getstack (&attribute, &bottom, &size) == 0);
  REQUIRE (size >= 65536 && size <= 2 * 1024 * 1024);
  if (current)
    REQUIRE ((uintptr_t) &attribute >= (uintptr_t) bottom
             && (uintptr_t) &attribute < (uintptr_t) bottom + size);
  REQUIRE (pthread_attr_destroy (&attribute) == 0);
}

static void *
worker (void *argument)
{
  unsigned id = (unsigned) (uintptr_t) argument;
  REQUIRE (tls_value == 73 && tls_zero == 0);
  tls_value = 1000 + id;
  tls_zero = id;
  errno = (int) (100 + id);
  REQUIRE (pthread_setspecific (key, argument) == 0);
  REQUIRE (pthread_getspecific (key) == argument);
  REQUIRE (pthread_once (&once, initialize_once) == 0);
  check_stack (pthread_self (), 1);
  REQUIRE ((unsigned long) pthread_gettid_np (pthread_self ())
           == (unsigned long) pthread_self ());
  REQUIRE (pthread_mutex_lock (&lock) == 0);
  ++ready;
  REQUIRE (pthread_cond_broadcast (&condition) == 0);
  while (!start)
    REQUIRE (pthread_cond_wait (&condition, &lock) == 0);
  REQUIRE (pthread_mutex_unlock (&lock) == 0);
  REQUIRE (sem_wait (&gate) == 0);
  int barrier_result = pthread_barrier_wait (&barrier);
  REQUIRE (barrier_result == 0 || barrier_result == PTHREAD_BARRIER_SERIAL_THREAD);
  for (unsigned i = 0; i < 200; ++i)
    {
      REQUIRE (pthread_mutex_lock (&lock) == 0);
      ++operations;
      REQUIRE (pthread_mutex_unlock (&lock) == 0);
      REQUIRE (pthread_rwlock_rdlock (&rwlock) == 0);
      int snapshot = shared_value;
      REQUIRE (snapshot >= 0);
      REQUIRE (pthread_rwlock_unlock (&rwlock) == 0);
      REQUIRE (pthread_rwlock_wrlock (&rwlock) == 0);
      ++shared_value;
      REQUIRE (pthread_rwlock_unlock (&rwlock) == 0);
      REQUIRE (sched_yield () == 0);
      REQUIRE (tls_value == 1000 + id && tls_zero == id);
      REQUIRE (errno == (int) (100 + id));
    }
  unsigned char *allocation = malloc (4097);
  REQUIRE (allocation != NULL);
  memset (allocation, (int) id, 4097);
  for (unsigned i = 0; i < 4097; ++i)
    REQUIRE (allocation[i] == id);
  free (allocation);
  void *value = (void *) (uintptr_t) (0x1234567800000000ULL + id);
  if (id == 2)
    {
      pthread_cleanup_push (cleanup_value, (void *) 1);
      pthread_cleanup_push (cleanup_value, (void *) 2);
      pthread_exit (value);
      pthread_cleanup_pop (0);
      pthread_cleanup_pop (0);
    }
  return value;
}

static void
check_unsupported_attributes (void)
{
  pthread_mutexattr_t mutex, mutex_before;
  REQUIRE (pthread_mutexattr_init (&mutex) == 0);
  memcpy (&mutex_before, &mutex, sizeof (mutex));
  REQUIRE (pthread_mutexattr_setpshared (&mutex, PTHREAD_PROCESS_SHARED) == ENOTSUP);
  REQUIRE (pthread_mutexattr_setrobust (&mutex, PTHREAD_MUTEX_ROBUST) == ENOTSUP);
  REQUIRE (pthread_mutexattr_setprotocol (&mutex, PTHREAD_PRIO_INHERIT) == ENOTSUP);
  REQUIRE (pthread_mutexattr_setprotocol (&mutex, PTHREAD_PRIO_PROTECT) == ENOTSUP);
  REQUIRE (memcmp (&mutex, &mutex_before, sizeof (mutex)) == 0);
  REQUIRE (pthread_mutexattr_setpshared (&mutex, -1) == EINVAL);
  REQUIRE (pthread_mutexattr_setrobust (&mutex, -1) == EINVAL);
  REQUIRE (pthread_mutexattr_setprotocol (&mutex, -1) == EINVAL);
  REQUIRE (pthread_mutexattr_destroy (&mutex) == 0);

  pthread_condattr_t cond, cond_before;
  REQUIRE (pthread_condattr_init (&cond) == 0);
  memcpy (&cond_before, &cond, sizeof (cond));
  REQUIRE (pthread_condattr_setpshared (&cond, PTHREAD_PROCESS_SHARED) == ENOTSUP);
  REQUIRE (memcmp (&cond, &cond_before, sizeof (cond)) == 0);
  REQUIRE (pthread_condattr_destroy (&cond) == 0);

  pthread_rwlockattr_t rw;
  REQUIRE (pthread_rwlockattr_init (&rw) == 0);
  REQUIRE (pthread_rwlockattr_setpshared (&rw, PTHREAD_PROCESS_SHARED) == ENOTSUP);
  REQUIRE (pthread_rwlockattr_destroy (&rw) == 0);
  pthread_barrierattr_t bar;
  REQUIRE (pthread_barrierattr_init (&bar) == 0);
  REQUIRE (pthread_barrierattr_setpshared (&bar, PTHREAD_PROCESS_SHARED) == ENOTSUP);
  REQUIRE (pthread_barrierattr_destroy (&bar) == 0);

  int previous = 99;
  REQUIRE (pthread_setcanceltype (PTHREAD_CANCEL_ASYNCHRONOUS, &previous) == ENOTSUP);
  REQUIRE (previous == 99);
  REQUIRE (pthread_setcanceltype (PTHREAD_CANCEL_DEFERRED, &previous) == 0);
  REQUIRE (previous == PTHREAD_CANCEL_DEFERRED);
  errno = EDOM;
  REQUIRE (pthread_cancel (pthread_self ()) == ENOTSUP && errno == EDOM);
  puts ("G3-T PASS unsupported attributes and cancellation errors");
}

static void
check_timed_waits (void)
{
  struct timespec deadline = deadline_after (CLOCK_REALTIME, 40000000);
  REQUIRE (pthread_mutex_lock (&lock) == 0);
  REQUIRE (pthread_cond_timedwait (&condition, &lock, &deadline) == ETIMEDOUT);
  check_deadline_reached (CLOCK_REALTIME, deadline);
  REQUIRE (pthread_mutex_trylock (&lock) == EBUSY);
  REQUIRE (pthread_mutex_unlock (&lock) == 0);

  pthread_condattr_t attribute;
  pthread_cond_t monotonic;
  REQUIRE (pthread_condattr_init (&attribute) == 0);
  REQUIRE (pthread_condattr_setclock (&attribute, CLOCK_MONOTONIC) == 0);
  REQUIRE (pthread_cond_init (&monotonic, &attribute) == 0);
  REQUIRE (pthread_condattr_destroy (&attribute) == 0);
  deadline = deadline_after (CLOCK_MONOTONIC, 40000000);
  REQUIRE (pthread_mutex_lock (&lock) == 0);
  REQUIRE (pthread_cond_timedwait (&monotonic, &lock, &deadline) == ETIMEDOUT);
  check_deadline_reached (CLOCK_MONOTONIC, deadline);
  REQUIRE (pthread_mutex_unlock (&lock) == 0);
  REQUIRE (pthread_cond_destroy (&monotonic) == 0);

  deadline = deadline_after (CLOCK_REALTIME, 40000000);
  REQUIRE (sem_timedwait (&gate, &deadline) == -1 && errno == ETIMEDOUT);
  check_deadline_reached (CLOCK_REALTIME, deadline);
  deadline = deadline_after (CLOCK_REALTIME, 40000000);
  REQUIRE (pthread_mutex_lock (&lock) == 0);
  REQUIRE (pthread_mutex_timedlock (&lock, &deadline) == ETIMEDOUT);
  check_deadline_reached (CLOCK_REALTIME, deadline);
  REQUIRE (pthread_mutex_unlock (&lock) == 0);
  puts ("G3-T PASS monotonic and realtime bounded waits");
}

int
main (void)
{
  puts ("G3-T BEGIN public pthread probe");
  check_unsupported_attributes ();
  check_stack (pthread_self (), 1);
  REQUIRE (sem_init (&gate, 0, 0) == 0);
  REQUIRE (pthread_key_create (&key, destroy_value) == 0);
  REQUIRE (pthread_barrier_init (&barrier, NULL, 4) == 0);
  errno = EDOM;
  pthread_t threads[3];
  for (unsigned i = 0; i < 3; ++i)
    REQUIRE (pthread_create (&threads[i], NULL, worker, (void *) (uintptr_t) (i + 1)) == 0);
  REQUIRE (pthread_mutex_lock (&lock) == 0);
  while (ready != 3)
    REQUIRE (pthread_cond_wait (&condition, &lock) == 0);
  pthread_t extra = (pthread_t) ULONG_MAX;
  REQUIRE (pthread_create (&extra, NULL, worker, (void *) 1) == EAGAIN);
  REQUIRE (extra == (pthread_t) ULONG_MAX);
  for (unsigned i = 0; i < 3; ++i)
    check_stack (threads[i], 0);
  start = 1;
  REQUIRE (pthread_cond_broadcast (&condition) == 0);
  REQUIRE (pthread_mutex_unlock (&lock) == 0);
  for (unsigned i = 0; i < 10; ++i)
    REQUIRE (sched_yield () == 0);
  for (unsigned i = 0; i < 3; ++i)
    REQUIRE (sem_post (&gate) == 0);
  int barrier_result = pthread_barrier_wait (&barrier);
  REQUIRE (barrier_result == 0 || barrier_result == PTHREAD_BARRIER_SERIAL_THREAD);
  for (unsigned i = 0; i < 3; ++i)
    {
      void *value = NULL;
      REQUIRE (pthread_join (threads[i], &value) == 0);
      REQUIRE ((uintptr_t) value == 0x1234567800000001ULL + i);
      REQUIRE (pthread_join (threads[i], NULL) == ESRCH);
      REQUIRE (pthread_gettid_np (threads[i]) == -1);
      pthread_attr_t stale, before;
      memset (&stale, 0xa5, sizeof (stale));
      memcpy (&before, &stale, sizeof (stale));
      REQUIRE (pthread_getattr_np (threads[i], &stale) == ESRCH);
      REQUIRE (memcmp (&before, &stale, sizeof (stale)) == 0);
    }
  REQUIRE (pthread_join (pthread_self (), NULL) == EDEADLK);
  REQUIRE (destroyed == 3 && once_calls == 1 && operations == 600 && shared_value == 600);
  REQUIRE (cleanup_order == 21);
  REQUIRE (tls_value == 73 && tls_zero == 0 && errno == EDOM);
  puts ("G3-T PASS TLS errno once locks cond sem rwlock barrier TSD join exit quota");
  check_timed_waits ();
  REQUIRE (pthread_barrier_destroy (&barrier) == 0);
  REQUIRE (pthread_key_delete (key) == 0);
  REQUIRE (sem_destroy (&gate) == 0);
  REQUIRE (pthread_cond_destroy (&condition) == 0);
  REQUIRE (pthread_mutex_destroy (&lock) == 0);
  REQUIRE (pthread_rwlock_destroy (&rwlock) == 0);
  puts ("G3-T PASS complete");
  return 0;
}
