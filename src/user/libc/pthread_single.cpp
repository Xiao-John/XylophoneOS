// SPDX-License-Identifier: Apache-2.0
// Single-thread pthread subset for the ordinary (non-threaded) SDK.
// Mutexes, condition variables, rwlocks, once and TSS behave correctly for a
// one-threaded process; pthread_create/join/detach fail with ENOSYS so callers
// can tell that real threads need the threaded runtime.
#ifndef _POSIX_THREADS
#define _POSIX_THREADS 1
#endif
#ifndef _POSIX_READER_WRITER_LOCKS
#define _POSIX_READER_WRITER_LOCKS 200809L
#endif
#ifndef _UNIX98_THREAD_MUTEX_ATTRIBUTES
#define _UNIX98_THREAD_MUTEX_ATTRIBUTES 1
#endif
#include <errno.h>
#include <pthread.h>
#include <semaphore.h>
#include <string.h>
#include <xos/sdk.hpp>

#ifndef PTHREAD_PROCESS_PRIVATE
#define PTHREAD_PROCESS_PRIVATE 0
#endif

namespace {
constexpr unsigned key_count = 64;
void* key_values[key_count];
bool key_active[key_count];
pthread_key_t key_next;
char thread_name[16] = "main";
}  // namespace

extern "C" int pthread_once(pthread_once_t* once, void (*routine)(void)) {
    if (once == nullptr || routine == nullptr) { return EINVAL; }
    if (once->is_initialized && !once->init_executed) {
        once->init_executed = 1;
        routine();
    }
    return 0;
}

extern "C" int pthread_key_create(pthread_key_t* key, void (*)(void*)) {
    if (key == nullptr || key_next >= key_count) { return EAGAIN; }
    key_active[key_next] = true;
    *key = key_next++;
    return 0;
}

extern "C" int pthread_key_delete(pthread_key_t key) {
    if (key >= key_count || !key_active[key]) { return EINVAL; }
    key_active[key] = false;
    key_values[key] = nullptr;
    return 0;
}

extern "C" void* pthread_getspecific(pthread_key_t key) {
    return key < key_count && key_active[key] ? key_values[key] : nullptr;
}

extern "C" int pthread_setspecific(pthread_key_t key, const void* value) {
    if (key >= key_count || !key_active[key]) { return EINVAL; }
    key_values[key] = const_cast<void*>(value);
    return 0;
}

extern "C" int pthread_mutex_init(pthread_mutex_t*, const pthread_mutexattr_t*) { return 0; }
extern "C" int pthread_mutex_destroy(pthread_mutex_t*) { return 0; }
extern "C" int pthread_mutex_lock(pthread_mutex_t*) { return 0; }
extern "C" int pthread_mutex_trylock(pthread_mutex_t*) { return 0; }
extern "C" int pthread_mutex_timedlock(pthread_mutex_t*, const struct timespec*) { return 0; }
extern "C" int pthread_mutex_unlock(pthread_mutex_t*) { return 0; }

extern "C" int pthread_cond_init(pthread_cond_t*, const pthread_condattr_t*) { return 0; }
extern "C" int pthread_cond_destroy(pthread_cond_t*) { return 0; }
extern "C" int pthread_cond_signal(pthread_cond_t*) { return 0; }
extern "C" int pthread_cond_broadcast(pthread_cond_t*) { return 0; }
// A spurious wakeup is permitted; with one thread there is nobody to signal.
extern "C" int pthread_cond_wait(pthread_cond_t*, pthread_mutex_t*) { return 0; }
extern "C" int pthread_cond_timedwait(pthread_cond_t*, pthread_mutex_t*, const struct timespec*) { return 0; }
extern "C" int pthread_cond_clockwait(pthread_cond_t*, pthread_mutex_t*, clockid_t,
                                      const struct timespec*) { return 0; }

extern "C" int pthread_rwlock_init(pthread_rwlock_t*, const pthread_rwlockattr_t*) { return 0; }
extern "C" int pthread_rwlock_destroy(pthread_rwlock_t*) { return 0; }
extern "C" int pthread_rwlock_rdlock(pthread_rwlock_t*) { return 0; }
extern "C" int pthread_rwlock_tryrdlock(pthread_rwlock_t*) { return 0; }
extern "C" int pthread_rwlock_wrlock(pthread_rwlock_t*) { return 0; }
extern "C" int pthread_rwlock_trywrlock(pthread_rwlock_t*) { return 0; }
extern "C" int pthread_rwlock_unlock(pthread_rwlock_t*) { return 0; }
extern "C" int pthread_rwlockattr_init(pthread_rwlockattr_t*) { return 0; }
extern "C" int pthread_rwlockattr_destroy(pthread_rwlockattr_t*) { return 0; }
extern "C" int pthread_rwlockattr_setpshared(pthread_rwlockattr_t*, int) { return 0; }
extern "C" int pthread_rwlockattr_getpshared(const pthread_rwlockattr_t*, int* shared) {
    if (shared != nullptr) { *shared = PTHREAD_PROCESS_PRIVATE; }
    return 0;
}

extern "C" int pthread_mutexattr_init(pthread_mutexattr_t*) { return 0; }
extern "C" int pthread_mutexattr_destroy(pthread_mutexattr_t*) { return 0; }
extern "C" int pthread_mutexattr_settype(pthread_mutexattr_t*, int) { return 0; }
extern "C" int pthread_mutexattr_gettype(const pthread_mutexattr_t*, int* type) {
    if (type != nullptr) { *type = PTHREAD_MUTEX_DEFAULT; }
    return 0;
}
extern "C" int pthread_mutexattr_setpshared(pthread_mutexattr_t*, int) { return 0; }
extern "C" int pthread_mutexattr_setprotocol(pthread_mutexattr_t*, int) { return 0; }

extern "C" int pthread_condattr_init(pthread_condattr_t*) { return 0; }
extern "C" int pthread_condattr_destroy(pthread_condattr_t*) { return 0; }
extern "C" int pthread_condattr_setclock(pthread_condattr_t*, clockid_t) { return 0; }
extern "C" int pthread_condattr_getclock(const pthread_condattr_t*, clockid_t* clock_id) {
    if (clock_id != nullptr) { *clock_id = CLOCK_REALTIME; }
    return 0;
}
extern "C" int pthread_condattr_setpshared(pthread_condattr_t*, int) { return 0; }
extern "C" int pthread_condattr_getpshared(const pthread_condattr_t*, int* shared) {
    if (shared != nullptr) { *shared = PTHREAD_PROCESS_PRIVATE; }
    return 0;
}

extern "C" int pthread_attr_init(pthread_attr_t*) { return 0; }
extern "C" int pthread_attr_destroy(pthread_attr_t*) { return 0; }
extern "C" int pthread_attr_setstacksize(pthread_attr_t*, size_t) { return 0; }
extern "C" int pthread_attr_setdetachstate(pthread_attr_t*, int) { return 0; }
extern "C" int pthread_attr_setinheritsched(pthread_attr_t*, int) { return 0; }
extern "C" int pthread_attr_setschedpolicy(pthread_attr_t*, int) { return 0; }
extern "C" int pthread_attr_setscope(pthread_attr_t*, int) { return 0; }
extern "C" int pthread_attr_getstacksize(const pthread_attr_t*, size_t* size) {
    if (size != nullptr) { *size = 0; }
    return 0;
}
extern "C" int pthread_attr_getdetachstate(const pthread_attr_t*, int* state) {
    if (state != nullptr) { *state = PTHREAD_CREATE_JOINABLE; }
    return 0;
}

extern "C" int pthread_create(pthread_t*, const pthread_attr_t*, void* (*)(void*), void*) {
    errno = ENOSYS;
    return ENOSYS;
}
extern "C" int pthread_join(pthread_t, void**) { return ENOSYS; }
extern "C" int pthread_detach(pthread_t) { return ENOSYS; }
extern "C" int pthread_cancel(pthread_t) { return ENOSYS; }
extern "C" void pthread_exit(void* value) { (void)value; xos::sdk::exit(0); }
extern "C" pthread_t pthread_self(void) { return 1; }
extern "C" int pthread_equal(pthread_t left, pthread_t right) { return left == right; }
extern "C" int pthread_setcancelstate(int, int*) { return 0; }
extern "C" int pthread_setcanceltype(int, int*) { return 0; }
extern "C" int pthread_atfork(void (*)(void), void (*)(void), void (*)(void)) { return 0; }
extern "C" int sched_yield(void) { xos::sdk::yield(); return 0; }
extern "C" int pthread_setname_np(pthread_t, const char* name) {
    if (name == nullptr) { return EINVAL; }
    strncpy(thread_name, name, sizeof(thread_name) - 1);
    thread_name[sizeof(thread_name) - 1] = '\0';
    return 0;
}
extern "C" int pthread_getname_np(pthread_t, char* name, size_t size) {
    if (name == nullptr || size == 0) { return EINVAL; }
    strncpy(name, thread_name, size - 1);
    name[size - 1] = '\0';
    return 0;
}

extern "C" int sem_init(sem_t* sem, int pshared, unsigned value) {
    if (sem == nullptr) { return EINVAL; }
    if (pshared != 0) { return ENOSYS; }
    sem->value = value;
    sem->pshared = pshared;
    sem->initialized = 1;
    return 0;
}
extern "C" int sem_destroy(sem_t* sem) {
    if (sem == nullptr || !sem->initialized) { return EINVAL; }
    sem->initialized = 0;
    return 0;
}
extern "C" int sem_wait(sem_t* sem) {
    if (sem == nullptr || !sem->initialized) { return EINVAL; }
    while (sem->value == 0) { sched_yield(); }
    --sem->value;
    return 0;
}
extern "C" int sem_trywait(sem_t* sem) {
    if (sem == nullptr || !sem->initialized) { return EINVAL; }
    if (sem->value == 0) { return EAGAIN; }
    --sem->value;
    return 0;
}
extern "C" int sem_timedwait(sem_t* sem, const struct timespec*) {
    return sem_trywait(sem);
}
extern "C" int sem_post(sem_t* sem) {
    if (sem == nullptr || !sem->initialized) { return EINVAL; }
    ++sem->value;
    return 0;
}
extern "C" int sem_getvalue(sem_t* sem, int* value) {
    if (sem == nullptr || value == nullptr || !sem->initialized) { return EINVAL; }
    *value = static_cast<int>(sem->value);
    return 0;
}
extern "C" int pthread_barrier_init(pthread_barrier_t* barrier, const void*, unsigned count) {
    if (barrier == nullptr || count == 0) { return EINVAL; }
    barrier->count = count;
    barrier->waiting = 0;
    barrier->generation = 0;
    return 0;
}
extern "C" int pthread_barrier_destroy(pthread_barrier_t* barrier) {
    return barrier == nullptr ? EINVAL : 0;
}
extern "C" int pthread_barrier_wait(pthread_barrier_t* barrier) {
    if (barrier == nullptr || barrier->count == 0) { return EINVAL; }
    if (barrier->count != 1) {
        // No other thread can arrive in the single-thread runtime.
        while (true) { sched_yield(); }
    }
    return PTHREAD_BARRIER_SERIAL_THREAD;
}
extern "C" int pthread_spin_init(pthread_spinlock_t* lock, int) {
    if (lock == nullptr) { return EINVAL; }
    __atomic_store_n(lock, 0, __ATOMIC_RELEASE);
    return 0;
}
extern "C" int pthread_spin_destroy(pthread_spinlock_t* lock) {
    return lock == nullptr ? EINVAL : 0;
}
extern "C" int pthread_spin_lock(pthread_spinlock_t* lock) {
    if (lock == nullptr) { return EINVAL; }
    while (__atomic_exchange_n(lock, 1, __ATOMIC_ACQUIRE) != 0) { sched_yield(); }
    return 0;
}
extern "C" int pthread_spin_trylock(pthread_spinlock_t* lock) {
    if (lock == nullptr) { return EINVAL; }
    return __atomic_exchange_n(lock, 1, __ATOMIC_ACQUIRE) == 0 ? 0 : EBUSY;
}
extern "C" int pthread_spin_unlock(pthread_spinlock_t* lock) {
    if (lock == nullptr) { return EINVAL; }
    __atomic_store_n(lock, 0, __ATOMIC_RELEASE);
    return 0;
}
extern "C" int pthread_attr_getguardsize(const pthread_attr_t*, size_t* size) {
    if (size == nullptr) { return EINVAL; }
    *size = 0;
    return 0;
}
extern "C" int pthread_attr_setguardsize(pthread_attr_t*, size_t size) {
    return size == 0 ? 0 : ENOTSUP;
}
extern "C" int pthread_tryjoin_np(pthread_t, void**) { return ENOTSUP; }
extern "C" int pthread_timedjoin_np(pthread_t, void**, const struct timespec*) { return ENOTSUP; }
extern "C" int pthread_getcpuclockid(pthread_t, clockid_t*) { return ENOTSUP; }
