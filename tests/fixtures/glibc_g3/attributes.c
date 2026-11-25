/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <pthreadP.h>
#include <stdint.h>
#include "xos_thread_identity.h"
#include "xos_thread_name.h"

static pthread_t current = 100;
static xos_i64 native_error;
pthread_t __pthread_self (void) { return current; }
int __pthread_attr_init (pthread_attr_t *attribute) { return pthread_attr_init (attribute); }
xos_i64
__xos_thread_identity_test_call (xos_u64 number, xos_u64 first, xos_u64 second)
{
  assert (number == 41 && second == 0);
  if (native_error)
    return native_error;
  struct xos_thread_info *info = (void *) first;
  *info = (struct xos_thread_info) { .tid = current, .stack_bottom = 0x40000000,
                                   .stack_top = 0x40020000 };
  return 0;
}

int __pthread_mutexattr_setpshared (pthread_mutexattr_t *, int);
int __pthread_condattr_setpshared (pthread_condattr_t *, int);
int __pthread_rwlockattr_setpshared (pthread_rwlockattr_t *, int);
int __pthread_barrierattr_setpshared (pthread_barrierattr_t *, int);
int __pthread_mutexattr_setrobust (pthread_mutexattr_t *, int);
int __pthread_mutexattr_setprotocol (pthread_mutexattr_t *, int);
int __pthread_setcanceltype (int, int *);
int __pthread_getattr_np (pthread_t, pthread_attr_t *);
pid_t pthread_gettid_np (pthread_t);

#define CHECK_SHARED(kind) do { \
  pthread_##kind##attr_t attribute, before; \
  assert (pthread_##kind##attr_init (&attribute) == 0); \
  memcpy (&before, &attribute, sizeof (before)); \
  assert (__pthread_##kind##attr_setpshared (&attribute, PTHREAD_PROCESS_SHARED) == ENOTSUP); \
  assert (__pthread_##kind##attr_setpshared (&attribute, -1) == EINVAL); \
  assert (memcmp (&before, &attribute, sizeof (attribute)) == 0); \
  assert (__pthread_##kind##attr_setpshared (&attribute, PTHREAD_PROCESS_PRIVATE) == 0); \
  assert (pthread_##kind##attr_destroy (&attribute) == 0); \
} while (0)

int
main (void)
{
  errno = EDOM;
  CHECK_SHARED (mutex);
  CHECK_SHARED (cond);
  CHECK_SHARED (rwlock);
  CHECK_SHARED (barrier);
  pthread_mutexattr_t mutex, before;
  assert (pthread_mutexattr_init (&mutex) == 0);
  memcpy (&before, &mutex, sizeof (mutex));
  assert (__pthread_mutexattr_setrobust (&mutex, PTHREAD_MUTEX_ROBUST) == ENOTSUP);
  assert (__pthread_mutexattr_setrobust (&mutex, -1) == EINVAL);
  assert (__pthread_mutexattr_setprotocol (&mutex, PTHREAD_PRIO_INHERIT) == ENOTSUP);
  assert (__pthread_mutexattr_setprotocol (&mutex, PTHREAD_PRIO_PROTECT) == ENOTSUP);
  assert (__pthread_mutexattr_setprotocol (&mutex, -1) == EINVAL);
  assert (memcmp (&before, &mutex, sizeof (mutex)) == 0);
  assert (__pthread_mutexattr_setrobust (&mutex, PTHREAD_MUTEX_STALLED) == 0);
  assert (__pthread_mutexattr_setprotocol (&mutex, PTHREAD_PRIO_NONE) == 0);
  assert (pthread_mutexattr_destroy (&mutex) == 0);
  int old = 99;
  assert (__pthread_setcanceltype (PTHREAD_CANCEL_ASYNCHRONOUS, &old) == ENOTSUP && old == 99);
  assert (__pthread_setcanceltype (-1, &old) == EINVAL && old == 99);
  assert (__pthread_setcanceltype (PTHREAD_CANCEL_DEFERRED, &old) == 0 && old == PTHREAD_CANCEL_DEFERRED);
  assert (__pthread_setcanceltype (PTHREAD_CANCEL_DEFERRED, NULL) == 0);

  assert (pthread_gettid_np (current) == (pid_t) current);
  assert (pthread_gettid_np (0) == -1);
  assert (pthread_gettid_np (ULONG_MAX) == -1);
  pthread_attr_t attribute, snapshot;
  assert (__pthread_getattr_np (current, &attribute) == 0);
  void *bottom;
  size_t size;
  assert (pthread_attr_getstack (&attribute, &bottom, &size) == 0);
  assert ((uintptr_t) bottom == 0x40000000 && size == 0x20000);
  assert (pthread_attr_destroy (&attribute) == 0);

  assert (__xos_thread_name_add (101) == 0);
  struct xos_thread_attributes value = { 0x70000000, 0x70040000, 4096, 0 };
  assert (__xos_thread_attributes_set (101, &value) == 0);
  assert (pthread_gettid_np (101) == 101);
  assert (__pthread_getattr_np (101, &attribute) == 0);
  assert (pthread_attr_getstack (&attribute, &bottom, &size) == 0);
  assert ((uintptr_t) bottom == 0x70000000 && size == 0x40000);
  assert (pthread_attr_getguardsize (&attribute, &size) == 0 && size == 4096);
  assert (pthread_attr_destroy (&attribute) == 0);
  __xos_thread_attributes_detach (101);
  assert (__pthread_getattr_np (101, &attribute) == 0);
  int detached;
  assert (pthread_attr_getdetachstate (&attribute, &detached) == 0 && detached == PTHREAD_CREATE_DETACHED);
  assert (pthread_attr_destroy (&attribute) == 0);
  __xos_thread_name_remove (101);
  assert (pthread_gettid_np (101) == -1);
  memset (&attribute, 0xa5, sizeof (attribute));
  memcpy (&snapshot, &attribute, sizeof (attribute));
  assert (__pthread_getattr_np (101, &attribute) == ESRCH);
  assert (memcmp (&snapshot, &attribute, sizeof (attribute)) == 0);
  native_error = -11;
  assert (__pthread_getattr_np (current, &attribute) == EFAULT);
  assert (memcmp (&snapshot, &attribute, sizeof (attribute)) == 0);
  assert (errno == EDOM);
  return 0;
}
