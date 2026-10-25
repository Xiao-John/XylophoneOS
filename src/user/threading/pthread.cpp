// SPDX-License-Identifier: Apache-2.0
#include "runtime.hpp"
#include <errno.h>
#include <stdint.h>
#include <limits.h>
using namespace xos;
namespace {
pthread_mutex_t creation_lock = PTHREAD_MUTEX_INITIALIZER;
pthread_mutex_t keys_lock = PTHREAD_MUTEX_INITIALIZER;
struct key_record { bool active; unsigned generation; void (*destructor)(void*); } keys[PTHREAD_KEYS_MAX];
int error(i64 result) {
    switch (result) {
    case 0: return 0;
    case thread_error_address: return EFAULT;
    case process_error_invalid: return EINVAL;
    case process_error_denied: return EPERM;
    case process_error_resources: return EAGAIN;
    case thread_error_memory: return ENOMEM;
    case process_error_state: case thread_error_busy: return EBUSY;
    case thread_error_timeout: return ETIMEDOUT;
    case thread_error_not_found: return ESRCH;
    case thread_error_deadlock: return EDEADLK;
    case thread_error_unsupported: return ENOTSUP;
    default: return EIO;
    }
}
int deadline(const timespec* time, u64& value) {
    if (!time || time->tv_sec < 0 || time->tv_nsec < 0 || time->tv_nsec >= 1000000000) { return EINVAL; }
    const u64 seconds = static_cast<u64>(time->tv_sec), nanos = static_cast<u64>(time->tv_nsec);
    if (seconds > (thread_deadline_infinite - 1 - nanos) / 1000000000) { return EINVAL; }
    value = seconds * 1000000000 + nanos; return 0;
}
bool valid(const pthread_mutex_t* mutex) { return mutex && __atomic_load_n(&mutex->valid, __ATOMIC_ACQUIRE) == 1; }
int try_mutex(pthread_mutex_t* mutex, u64 tid) {
    if (!valid(mutex)) { return EINVAL; }
    if (__atomic_load_n(&mutex->owner, __ATOMIC_RELAXED) == tid) {
        if (mutex->type == PTHREAD_MUTEX_RECURSIVE) {
            if (mutex->depth == UINT_MAX) { return EAGAIN; }
            ++mutex->depth; return 0;
        }
        return EBUSY;
    }
    u32 expected = 0;
    if (!__atomic_compare_exchange_n(&mutex->lock, &expected, 1, false, __ATOMIC_ACQUIRE, __ATOMIC_RELAXED)) { return EBUSY; }
    __atomic_store_n(&mutex->owner, tid, __ATOMIC_RELAXED);
    mutex->depth = 1; return 0;
}
int condition_wait(pthread_cond_t* cond, pthread_mutex_t* mutex, u64 until) {
    if (!cond || __atomic_load_n(&cond->valid, __ATOMIC_ACQUIRE) != 1 || !valid(mutex)) { return EINVAL; }
    if (mutex->depth != 1 || __atomic_load_n(&mutex->owner, __ATOMIC_RELAXED) != pthread_self()) { return EINVAL; }
    const u32 sequence = __atomic_load_n(&cond->sequence, __ATOMIC_ACQUIRE);
    __atomic_fetch_add(&cond->waiters, 1u, __ATOMIC_ACQ_REL);
    const int released = pthread_mutex_unlock(mutex);
    if (released) { __atomic_fetch_sub(&cond->waiters, 1u, __ATOMIC_RELEASE); return released; }
    const i64 waited = thread::wait(&cond->sequence, sequence, until);
    const int acquired = pthread_mutex_lock(mutex);
    __atomic_fetch_sub(&cond->waiters, 1u, __ATOMIC_RELEASE);
    if (acquired) { return acquired; }
    return waited == 0 || waited == thread_value_changed ? 0 : error(waited);
}
struct once_frame {
    pthread_once_t* once;
    once_frame* previous;
    bool completed;
    void reset() {
        if (!completed) {
            __atomic_store_n(&once->owner, u64{0}, __ATOMIC_RELAXED);
            __atomic_store_n(&once->state, 0u, __ATOMIC_RELEASE);
            (void)thread::wake(&once->state, UINT_MAX);
        }
    }
    ~once_frame() { reset(); xos_current_control()->once_active = previous; }
};
}
extern "C" pthread_t pthread_self() { return thread::self(); }
extern "C" int pthread_equal(pthread_t a, pthread_t b) { return a == b; }
extern "C" int pthread_create(pthread_t* id, const pthread_attr_t* attr, void*(*entry)(void*), void* argument) {
    if (!id || !entry || (attr && !attr->valid)) { return EINVAL; }
    if (attr && attr->stackaddr) { return ENOTSUP; }
    if (attr && attr->detachstate != PTHREAD_CREATE_JOINABLE && attr->detachstate != PTHREAD_CREATE_DETACHED) { return EINVAL; }
    const int initialized = xos_thread_runtime_init(); if (initialized) { return initialized; }
    int status = pthread_mutex_lock(&creation_lock); if (status) { return status; }
    const i64 created = xos_allocate_thread(id, entry, argument,
        attr ? attr->stacksize : thread_stack_default, attr && attr->detachstate == PTHREAD_CREATE_DETACHED);
    pthread_mutex_unlock(&creation_lock); return error(created);
}
extern "C" int pthread_join(pthread_t id, void** output) {
    u64 value = 0; const i64 joined = thread::join(id, value);
    if (joined == 0 && output) { *output = reinterpret_cast<void*>(value); }
    return error(joined);
}
extern "C" int pthread_detach(pthread_t id) { return error(thread::detach(id)); }
extern "C" int xos_thread_cleanup_active() {
    auto* control = xos_current_control(); return control && control->cleanup_started;
}
extern "C" void xos_thread_cleanup() {
    auto* control = xos_current_control();
    if (control->cleanup_started) { sdk::exit(126); }
    control->cleanup_started = true;
    xos_cpp_tls_cleanup();
    for (unsigned round = 0; round < PTHREAD_DESTRUCTOR_ITERATIONS; ++round) {
        bool invoked = false;
        for (unsigned i = 0; i < PTHREAD_KEYS_MAX; ++i) {
            void (*destructor)(void*) = nullptr; void* value = nullptr;
            pthread_mutex_lock(&keys_lock);
            if (keys[i].active && control->keys[i].generation == keys[i].generation) {
                value = control->keys[i].value;
                destructor = keys[i].destructor;
            }
            control->keys[i].value = nullptr;
            pthread_mutex_unlock(&keys_lock);
            if (value && destructor) { invoked = true; destructor(value); }
        }
        if (!invoked) { break; }
    }
    while (control->once_active) {
        auto* frame = static_cast<once_frame*>(control->once_active);
        frame->reset(); control->once_active = frame->previous;
    }
    _reclaim_reent(&control->reent);
    // The elected final thread may now run process atexit/stdio callbacks. Give
    // those callbacks an empty but valid reent after reclaiming thread state.
    _REENT_INIT_PTR(&control->reent);
}
extern "C" void pthread_exit(void* value) {
    xos_thread_cleanup();
    const i64 last = sdk::syscall(sys_thread_begin_exit);
    if (last == 1) { xos_thread_process_finish(0); }
    if (last != 0) { sdk::exit(126); }
    (void)sdk::syscall(sys_thread_exit, reinterpret_cast<u64>(value));
    sdk::exit(126);
}
extern "C" int pthread_attr_init(pthread_attr_t* attr) {
    if (!attr) { return EINVAL; } *attr = {thread_stack_default, nullptr, PTHREAD_CREATE_JOINABLE, 1}; return 0;
}
extern "C" int pthread_attr_destroy(pthread_attr_t* attr) {
    if (!attr || !attr->valid) { return EINVAL; } attr->valid = 0; return 0;
}
extern "C" int pthread_attr_getdetachstate(const pthread_attr_t* attr, int* state) {
    if (!attr || !attr->valid || !state) { return EINVAL; } *state = attr->detachstate; return 0;
}
extern "C" int pthread_attr_setdetachstate(pthread_attr_t* attr, int state) {
    if (!attr || !attr->valid || (state != PTHREAD_CREATE_JOINABLE && state != PTHREAD_CREATE_DETACHED)) { return EINVAL; }
    attr->detachstate = state; return 0;
}
extern "C" int pthread_attr_getstacksize(const pthread_attr_t* attr, size_t* size) {
    if (!attr || !attr->valid || !size) { return EINVAL; } *size = attr->stacksize; return 0;
}
extern "C" int pthread_attr_setstacksize(pthread_attr_t* attr, size_t size) {
    if (!attr || !attr->valid || size < thread_stack_min || size > thread_stack_max || size % 4096) { return EINVAL; }
    attr->stacksize = size; return 0;
}
extern "C" int pthread_attr_getstack(const pthread_attr_t* attr, void** address, size_t* size) {
    if (!attr || !attr->valid || !address || !size || !attr->stackaddr) { return EINVAL; }
    *address = attr->stackaddr; *size = attr->stacksize; return 0;
}
extern "C" int pthread_attr_setstack(pthread_attr_t* attr, void*, size_t) { return attr && attr->valid ? ENOTSUP : EINVAL; }
extern "C" int pthread_attr_setschedpolicy(pthread_attr_t* attr, int) { return attr && attr->valid ? ENOTSUP : EINVAL; }
extern "C" int pthread_attr_setinheritsched(pthread_attr_t* attr, int) { return attr && attr->valid ? ENOTSUP : EINVAL; }
extern "C" int pthread_attr_setscope(pthread_attr_t* attr, int) { return attr && attr->valid ? ENOTSUP : EINVAL; }
extern "C" int pthread_getattr_np(pthread_t id, pthread_attr_t* attr) {
    if (!attr) { return EINVAL; } if (id != pthread_self()) { return ENOTSUP; }
    thread_info info{}; const i64 result = thread::info(info); if (result < 0) { return error(result); }
    *attr = {info.stack_top - info.stack_bottom, reinterpret_cast<void*>(info.stack_bottom), PTHREAD_CREATE_JOINABLE, 1}; return 0;
}
extern "C" int pthread_mutexattr_init(pthread_mutexattr_t* attr) {
    if (!attr) { return EINVAL; } *attr = {PTHREAD_MUTEX_NORMAL, 1}; return 0;
}
extern "C" int pthread_mutexattr_destroy(pthread_mutexattr_t* attr) {
    if (!attr || !attr->valid) { return EINVAL; } attr->valid = 0; return 0;
}
extern "C" int pthread_mutexattr_settype(pthread_mutexattr_t* attr, int type) {
    if (!attr || !attr->valid || type < PTHREAD_MUTEX_NORMAL || type > PTHREAD_MUTEX_RECURSIVE) { return EINVAL; }
    attr->type = type; return 0;
}
extern "C" int pthread_mutexattr_gettype(const pthread_mutexattr_t* attr, int* type) {
    if (!attr || !attr->valid || !type) { return EINVAL; } *type = attr->type; return 0;
}
extern "C" int pthread_mutexattr_setpshared(pthread_mutexattr_t* attr, int sharing) {
    if (!attr || !attr->valid) { return EINVAL; } return sharing == PTHREAD_PROCESS_PRIVATE ? 0 : sharing == PTHREAD_PROCESS_SHARED ? ENOTSUP : EINVAL;
}
extern "C" int pthread_mutexattr_setprotocol(pthread_mutexattr_t* attr, int) { return attr && attr->valid ? ENOTSUP : EINVAL; }
extern "C" int pthread_mutex_init(pthread_mutex_t* mutex, const pthread_mutexattr_t* attr) {
    if (!mutex || (attr && !attr->valid)) { return EINVAL; }
    *mutex = pthread_mutex_t PTHREAD_MUTEX_INITIALIZER;
    mutex->type = attr ? static_cast<u32>(attr->type) : PTHREAD_MUTEX_NORMAL; return 0;
}
extern "C" int pthread_mutex_destroy(pthread_mutex_t* mutex) {
    if (!valid(mutex)) { return EINVAL; }
    if (__atomic_load_n(&mutex->lock, __ATOMIC_ACQUIRE) || __atomic_load_n(&mutex->waiters, __ATOMIC_ACQUIRE)) { return EBUSY; }
    __atomic_store_n(&mutex->valid, 0u, __ATOMIC_RELEASE); return 0;
}
extern "C" int pthread_mutex_trylock(pthread_mutex_t* mutex) { return try_mutex(mutex, pthread_self()); }
extern "C" int pthread_mutex_lock(pthread_mutex_t* mutex) {
    const u64 tid = pthread_self();
    int status = try_mutex(mutex, tid); if (status != EBUSY) { return status; }
    if (mutex->type == PTHREAD_MUTEX_ERRORCHECK && __atomic_load_n(&mutex->owner, __ATOMIC_RELAXED) == tid) { return EDEADLK; }
    __atomic_fetch_add(&mutex->waiters, 1u, __ATOMIC_ACQ_REL);
    while ((status = try_mutex(mutex, tid)) == EBUSY) {
        const i64 waited = thread::wait(&mutex->lock, 1);
        if (waited != 0 && waited != thread_value_changed) { status = error(waited); break; }
    }
    __atomic_fetch_sub(&mutex->waiters, 1u, __ATOMIC_RELEASE); return status;
}
extern "C" int pthread_mutex_unlock(pthread_mutex_t* mutex) {
    if (!valid(mutex)) { return EINVAL; }
    if (__atomic_load_n(&mutex->owner, __ATOMIC_RELAXED) != pthread_self() || mutex->depth == 0) { return EPERM; }
    if (--mutex->depth != 0) { return 0; }
    __atomic_store_n(&mutex->owner, u64{0}, __ATOMIC_RELAXED);
    __atomic_store_n(&mutex->lock, 0u, __ATOMIC_RELEASE);
    (void)thread::wake(&mutex->lock); return 0;
}
extern "C" int pthread_condattr_init(pthread_condattr_t* attr) {
    if (!attr) { return EINVAL; } *attr = {CLOCK_REALTIME, 1}; return 0;
}
extern "C" int pthread_condattr_destroy(pthread_condattr_t* attr) {
    if (!attr || !attr->valid) { return EINVAL; } attr->valid = 0; return 0;
}
extern "C" int pthread_condattr_setclock(pthread_condattr_t* attr, clockid_t clock) {
    if (!attr || !attr->valid || (clock != CLOCK_MONOTONIC && clock != CLOCK_REALTIME)) { return EINVAL; }
    attr->clock = static_cast<int>(clock); return 0;
}
extern "C" int pthread_condattr_getclock(const pthread_condattr_t* attr, clockid_t* clock) {
    if (!attr || !attr->valid || !clock) { return EINVAL; } *clock = static_cast<clockid_t>(attr->clock); return 0;
}
extern "C" int pthread_condattr_setpshared(pthread_condattr_t* attr, int sharing) {
    if (!attr || !attr->valid) { return EINVAL; } return sharing == PTHREAD_PROCESS_PRIVATE ? 0 : sharing == PTHREAD_PROCESS_SHARED ? ENOTSUP : EINVAL;
}
extern "C" int pthread_cond_init(pthread_cond_t* cond, const pthread_condattr_t* attr) {
    if (!cond || (attr && !attr->valid)) { return EINVAL; }
    *cond = pthread_cond_t PTHREAD_COND_INITIALIZER; cond->clock = attr ? attr->clock : CLOCK_REALTIME; return 0;
}
extern "C" int pthread_cond_destroy(pthread_cond_t* cond) {
    if (!cond || __atomic_load_n(&cond->valid, __ATOMIC_ACQUIRE) != 1) { return EINVAL; }
    if (__atomic_load_n(&cond->waiters, __ATOMIC_ACQUIRE)) { return EBUSY; }
    __atomic_store_n(&cond->valid, 0u, __ATOMIC_RELEASE); return 0;
}
extern "C" int pthread_cond_wait(pthread_cond_t* cond, pthread_mutex_t* mutex) { return condition_wait(cond, mutex, thread_deadline_infinite); }
extern "C" int pthread_cond_clockwait(pthread_cond_t* cond, pthread_mutex_t* mutex, clockid_t clock, const timespec* timeout) {
    if (clock != CLOCK_MONOTONIC) { return clock == CLOCK_REALTIME ? ENOTSUP : EINVAL; }
    u64 until; const int status = deadline(timeout, until); if (status) { return status; }
    return condition_wait(cond, mutex, until);
}
extern "C" int pthread_cond_timedwait(pthread_cond_t* cond, pthread_mutex_t* mutex, const timespec* timeout) {
    if (!cond || cond->valid != 1) { return EINVAL; }
    return pthread_cond_clockwait(cond, mutex, static_cast<clockid_t>(cond->clock), timeout);
}
extern "C" int pthread_cond_signal(pthread_cond_t* cond) {
    if (!cond || __atomic_load_n(&cond->valid, __ATOMIC_ACQUIRE) != 1) { return EINVAL; }
    __atomic_fetch_add(&cond->sequence, 1u, __ATOMIC_RELEASE); (void)thread::wake(&cond->sequence); return 0;
}
extern "C" int pthread_cond_broadcast(pthread_cond_t* cond) {
    if (!cond || __atomic_load_n(&cond->valid, __ATOMIC_ACQUIRE) != 1) { return EINVAL; }
    __atomic_fetch_add(&cond->sequence, 1u, __ATOMIC_RELEASE); (void)thread::wake(&cond->sequence, UINT_MAX); return 0;
}
extern "C" int pthread_once(pthread_once_t* once, void(*initialize)()) {
    if (!once || !initialize) { return EINVAL; }
    for (;;) {
        u32 state = __atomic_load_n(&once->state, __ATOMIC_ACQUIRE);
        if (state == 2) { return 0; }
        if (state > 2) { return EINVAL; }
        if (state == 0 && __atomic_compare_exchange_n(&once->state, &state, 1u, false, __ATOMIC_ACQUIRE, __ATOMIC_RELAXED)) {
            __atomic_store_n(&once->owner, pthread_self(), __ATOMIC_RELAXED);
            auto* control = xos_current_control();
            once_frame frame{once, static_cast<once_frame*>(control->once_active), false};
            control->once_active = &frame;
            initialize();
            frame.completed = true;
            __atomic_store_n(&once->owner, u64{0}, __ATOMIC_RELAXED);
            __atomic_store_n(&once->state, 2u, __ATOMIC_RELEASE);
            thread::wake(&once->state, UINT_MAX); return 0;
        }
        if (__atomic_load_n(&once->owner, __ATOMIC_RELAXED) == pthread_self()) { return EDEADLK; }
        const i64 waited = thread::wait(&once->state, 1);
        if (waited != 0 && waited != thread_value_changed) { return error(waited); }
    }
}
extern "C" int pthread_key_create(pthread_key_t* key, void(*destructor)(void*)) {
    if (!key) { return EINVAL; }
    pthread_mutex_lock(&keys_lock);
    for (unsigned i = 0; i < PTHREAD_KEYS_MAX; ++i) {
        if (!keys[i].active && keys[i].generation < 0x3ffffffu) {
            ++keys[i].generation; keys[i].active = true; keys[i].destructor = destructor;
            *key = keys[i].generation * PTHREAD_KEYS_MAX + i;
            pthread_mutex_unlock(&keys_lock); return 0;
        }
    }
    pthread_mutex_unlock(&keys_lock); return EAGAIN;
}
extern "C" int pthread_key_delete(pthread_key_t key) {
    const unsigned index = key % PTHREAD_KEYS_MAX, generation = key / PTHREAD_KEYS_MAX;
    pthread_mutex_lock(&keys_lock);
    const bool active = keys[index].active && keys[index].generation == generation;
    if (active) { keys[index].active = false; keys[index].destructor = nullptr; }
    pthread_mutex_unlock(&keys_lock); return active ? 0 : EINVAL;
}
extern "C" void* pthread_getspecific(pthread_key_t key) {
    const unsigned index = key % PTHREAD_KEYS_MAX, generation = key / PTHREAD_KEYS_MAX;
    pthread_mutex_lock(&keys_lock);
    auto* control = xos_current_control();
    void* value = keys[index].active && keys[index].generation == generation && control->keys[index].generation == generation
        ? control->keys[index].value : nullptr;
    pthread_mutex_unlock(&keys_lock); return value;
}
extern "C" int pthread_setspecific(pthread_key_t key, const void* value) {
    const unsigned index = key % PTHREAD_KEYS_MAX, generation = key / PTHREAD_KEYS_MAX;
    pthread_mutex_lock(&keys_lock);
    const bool active = keys[index].active && keys[index].generation == generation;
    if (active) { xos_current_control()->keys[index] = {const_cast<void*>(value), generation}; }
    pthread_mutex_unlock(&keys_lock); return active ? 0 : EINVAL;
}
extern "C" int pthread_cancel(pthread_t) { return ENOTSUP; }
extern "C" int pthread_setcancelstate(int, int*) { return ENOTSUP; }
extern "C" int pthread_setcanceltype(int, int*) { return ENOTSUP; }
extern "C" int pthread_atfork(void(*)(), void(*)(), void(*)()) { return ENOTSUP; }
extern "C" int clock_gettime(clockid_t clock, timespec* value) {
    if (!value) { errno = EFAULT; return -1; }
    if (clock != CLOCK_MONOTONIC) { errno = clock == CLOCK_REALTIME ? ENOTSUP : EINVAL; return -1; }
    const u64 now = thread::clock(); value->tv_sec = static_cast<time_t>(now / 1000000000);
    value->tv_nsec = static_cast<long>(now % 1000000000); return 0;
}
extern "C" int clock_getres(clockid_t clock, timespec* value) {
    if (clock != CLOCK_MONOTONIC) { errno = clock == CLOCK_REALTIME ? ENOTSUP : EINVAL; return -1; }
    if (value) { value->tv_sec = 0; value->tv_nsec = static_cast<long>(sdk::syscall(sys_clock_monotonic, 1)); } return 0;
}
extern "C" int nanosleep(const timespec* duration, timespec* remainder) {
    u64 delta; int status = deadline(duration, delta);
    if (status) { errno = status; return -1; }
    const u64 now = thread::clock();
    if (delta > thread_deadline_infinite - 1 - now) { errno = EINVAL; return -1; }
    const i64 result = thread::sleep_until(now + delta);
    if (result < 0) { errno = error(result); return -1; }
    if (remainder) { *remainder = {0, 0}; } return 0;
}
// Interfaces referenced by GCC's generic POSIX gthread header but outside the
// declared XOS v1 surface. They must fail explicitly if an application calls them.
extern "C" int pthread_mutex_timedlock(pthread_mutex_t*, const timespec*) { return ENOTSUP; }
extern "C" int pthread_rwlock_rdlock(pthread_rwlock_t*) { return ENOTSUP; }
extern "C" int pthread_rwlock_tryrdlock(pthread_rwlock_t*) { return ENOTSUP; }
extern "C" int pthread_rwlock_wrlock(pthread_rwlock_t*) { return ENOTSUP; }
extern "C" int pthread_rwlock_trywrlock(pthread_rwlock_t*) { return ENOTSUP; }
extern "C" int pthread_rwlock_unlock(pthread_rwlock_t*) { return ENOTSUP; }
extern "C" int sched_yield() { xos::sdk::yield(); return 0; }
extern "C" unsigned sleep(unsigned seconds) {
    const timespec duration{static_cast<time_t>(seconds), 0};
    return nanosleep(&duration, nullptr) == 0 ? 0 : seconds;
}
extern "C" int usleep(useconds_t microseconds) {
    const timespec duration{static_cast<time_t>(microseconds / 1000000),
        static_cast<long>(microseconds % 1000000) * 1000};
    return nanosleep(&duration, nullptr);
}
// There is no entropy service in this profile. In particular, never satisfy
// newlib arc4random or std::random_device with a constant/fake random source.
extern "C" int getentropy(void*, size_t) { errno = ENOSYS; return -1; }
