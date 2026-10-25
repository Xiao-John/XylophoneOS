// SPDX-License-Identifier: Apache-2.0
#pragma once
#ifdef XOS_THREADED_RUNTIME
#include <pthread.h>
namespace xos::libc {
struct runtime_mutex {
    pthread_mutex_t value = PTHREAD_RECURSIVE_MUTEX_INITIALIZER_NP;
    void lock() { if (pthread_mutex_lock(&value)) { __builtin_trap(); } }
    void unlock() { if (pthread_mutex_unlock(&value)) { __builtin_trap(); } }
};
}
#else
namespace xos::libc { struct runtime_mutex { void lock() {} void unlock() {} }; }
#endif
namespace xos::libc {
struct runtime_guard {
    runtime_mutex& mutex;
    explicit runtime_guard(runtime_mutex& value) : mutex(value) { mutex.lock(); }
    ~runtime_guard() { mutex.unlock(); }
    runtime_guard(const runtime_guard&) = delete;
    runtime_guard& operator=(const runtime_guard&) = delete;
};
}
