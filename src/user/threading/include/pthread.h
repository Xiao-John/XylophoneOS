/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_PTHREAD_H
#define XOS_PTHREAD_H
#if defined(XOS_THREADED_RUNTIME)
/* The threaded runtime returns ENOTSUP from the rwlock operations, so do not
   claim POSIX reader/writer lock support there; only declare the objects. */
typedef struct { int pshared; } pthread_rwlockattr_t;
#else
/* Older newlib feature headers report reader/writer locks as unsupported;
   the single-thread runtime implements them, so expose the types. */
#ifdef _POSIX_READER_WRITER_LOCKS
#undef _POSIX_READER_WRITER_LOCKS
#endif
#define _POSIX_READER_WRITER_LOCKS 200809L
#endif
#ifndef _UNIX98_THREAD_MUTEX_ATTRIBUTES
#define _UNIX98_THREAD_MUTEX_ATTRIBUTES 1
#endif
#include <sys/types.h>
#include <sys/_pthreadtypes.h>
#include <time.h>
#include <sched.h>
#ifndef CLOCK_MONOTONIC
#define CLOCK_MONOTONIC 4
#endif
#ifndef CLOCK_PROCESS_CPUTIME_ID
#define CLOCK_PROCESS_CPUTIME_ID 2
#endif
#ifndef CLOCK_THREAD_CPUTIME_ID
#define CLOCK_THREAD_CPUTIME_ID 3
#endif
#ifdef __cplusplus
extern "C" {
#endif
#define PTHREAD_CREATE_JOINABLE 0
#define PTHREAD_CREATE_DETACHED 1
#define PTHREAD_PROCESS_PRIVATE 0
#define PTHREAD_PROCESS_SHARED 1
#define PTHREAD_MUTEX_NORMAL 0
#define PTHREAD_MUTEX_DEFAULT PTHREAD_MUTEX_NORMAL
#define PTHREAD_MUTEX_ERRORCHECK 1
#define PTHREAD_MUTEX_RECURSIVE 2
#define PTHREAD_STACK_MIN 65536
#define PTHREAD_KEYS_MAX 64
#define PTHREAD_DESTRUCTOR_ITERATIONS 4
#define PTHREAD_MUTEX_INITIALIZER {0,0,0,0,PTHREAD_MUTEX_NORMAL,1,0}
#define PTHREAD_RECURSIVE_MUTEX_INITIALIZER_NP {0,0,0,0,PTHREAD_MUTEX_RECURSIVE,1,0}
#define PTHREAD_COND_INITIALIZER {0,0,CLOCK_REALTIME,1}
#define PTHREAD_RWLOCK_INITIALIZER {0}
#if defined(XOS_THREADED_RUNTIME)
#define PTHREAD_ONCE_INIT {0,0,0}
#else
#define PTHREAD_ONCE_INIT {1,0}
#endif
#define PTHREAD_BARRIER_SERIAL_THREAD (-1)

typedef struct {
    pthread_mutex_t mutex;
    pthread_cond_t cond;
    unsigned count;
    unsigned waiting;
    unsigned generation;
} pthread_barrier_t;

typedef volatile int pthread_spinlock_t;


int sched_yield(void);
int clock_gettime(clockid_t, struct timespec*);
int clock_getres(clockid_t, struct timespec*);
int nanosleep(const struct timespec*, struct timespec*);
int pthread_create(pthread_t*, const pthread_attr_t*, void*(*)(void*), void*);
pthread_t pthread_self(void);
int pthread_equal(pthread_t, pthread_t);
int pthread_join(pthread_t, void**);
int pthread_detach(pthread_t);
void pthread_exit(void*) __attribute__((noreturn));
int pthread_attr_init(pthread_attr_t*);
int pthread_attr_destroy(pthread_attr_t*);
int pthread_attr_getdetachstate(const pthread_attr_t*, int*);
int pthread_attr_setdetachstate(pthread_attr_t*, int);
int pthread_attr_getstacksize(const pthread_attr_t*, size_t*);
int pthread_attr_setstacksize(pthread_attr_t*, size_t);
int pthread_attr_getstack(const pthread_attr_t*, void**, size_t*);
int pthread_attr_setstack(pthread_attr_t*, void*, size_t);
int pthread_attr_setschedpolicy(pthread_attr_t*, int);
int pthread_attr_setinheritsched(pthread_attr_t*, int);
int pthread_attr_setscope(pthread_attr_t*, int);
int pthread_getattr_np(pthread_t, pthread_attr_t*);
int pthread_mutexattr_init(pthread_mutexattr_t*);
int pthread_mutexattr_destroy(pthread_mutexattr_t*);
int pthread_mutexattr_settype(pthread_mutexattr_t*, int);
int pthread_mutexattr_gettype(const pthread_mutexattr_t*, int*);
int pthread_mutexattr_setpshared(pthread_mutexattr_t*, int);
int pthread_mutexattr_setprotocol(pthread_mutexattr_t*, int);
int pthread_mutex_init(pthread_mutex_t*, const pthread_mutexattr_t*);
int pthread_mutex_destroy(pthread_mutex_t*);
int pthread_mutex_lock(pthread_mutex_t*);
int pthread_mutex_trylock(pthread_mutex_t*);
int pthread_mutex_unlock(pthread_mutex_t*);
int pthread_mutex_timedlock(pthread_mutex_t*, const struct timespec*);
int pthread_rwlock_init(pthread_rwlock_t*, const pthread_rwlockattr_t*);
int pthread_rwlock_destroy(pthread_rwlock_t*);
int pthread_rwlock_rdlock(pthread_rwlock_t*);
int pthread_rwlock_tryrdlock(pthread_rwlock_t*);
int pthread_rwlock_wrlock(pthread_rwlock_t*);
int pthread_rwlock_trywrlock(pthread_rwlock_t*);
int pthread_rwlock_unlock(pthread_rwlock_t*);
int pthread_condattr_init(pthread_condattr_t*);
int pthread_condattr_destroy(pthread_condattr_t*);
int pthread_condattr_setclock(pthread_condattr_t*, clockid_t);
int pthread_condattr_getclock(const pthread_condattr_t*, clockid_t*);
int pthread_condattr_setpshared(pthread_condattr_t*, int);
int pthread_cond_init(pthread_cond_t*, const pthread_condattr_t*);
int pthread_cond_destroy(pthread_cond_t*);
int pthread_cond_wait(pthread_cond_t*, pthread_mutex_t*);
int pthread_cond_timedwait(pthread_cond_t*, pthread_mutex_t*, const struct timespec*);
int pthread_cond_clockwait(pthread_cond_t*, pthread_mutex_t*, clockid_t, const struct timespec*);
int pthread_cond_signal(pthread_cond_t*);
int pthread_cond_broadcast(pthread_cond_t*);
int pthread_once(pthread_once_t*, void(*)(void));
int pthread_key_create(pthread_key_t*, void(*)(void*));
int pthread_key_delete(pthread_key_t);
void* pthread_getspecific(pthread_key_t);
int pthread_setspecific(pthread_key_t, const void*);
int pthread_cancel(pthread_t);
int pthread_setcancelstate(int, int*);
int pthread_setcanceltype(int, int*);
int pthread_atfork(void(*)(void), void(*)(void), void(*)(void));
int pthread_barrier_init(pthread_barrier_t*, const void*, unsigned);
int pthread_barrier_destroy(pthread_barrier_t*);
int pthread_barrier_wait(pthread_barrier_t*);
int pthread_spin_init(pthread_spinlock_t*, int);
int pthread_spin_destroy(pthread_spinlock_t*);
int pthread_spin_lock(pthread_spinlock_t*);
int pthread_spin_trylock(pthread_spinlock_t*);
int pthread_spin_unlock(pthread_spinlock_t*);
int pthread_attr_getguardsize(const pthread_attr_t*, size_t*);
int pthread_attr_setguardsize(pthread_attr_t*, size_t);
int pthread_condattr_getpshared(const pthread_condattr_t*, int*);
int pthread_rwlockattr_init(pthread_rwlockattr_t*);
int pthread_rwlockattr_destroy(pthread_rwlockattr_t*);
int pthread_rwlockattr_setpshared(pthread_rwlockattr_t*, int);
int pthread_rwlockattr_getpshared(const pthread_rwlockattr_t*, int*);
int pthread_setname_np(pthread_t, const char*);
int pthread_getname_np(pthread_t, char*, size_t);
int pthread_tryjoin_np(pthread_t, void**);
int pthread_timedjoin_np(pthread_t, void**, const struct timespec*);
int pthread_getcpuclockid(pthread_t, clockid_t*);
#ifdef __cplusplus
}
#endif
#endif
