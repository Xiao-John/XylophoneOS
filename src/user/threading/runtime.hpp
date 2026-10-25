// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <pthread.h>
#include <string.h>
#include <sys/reent.h>
#include <xos/thread_core.hpp>
struct xos_thread_control {
    void* (*entry)(void*);
    void* argument;
    _reent reent;
    void* once_active;
    bool cleanup_started;
    struct { void* value; unsigned generation; } keys[PTHREAD_KEYS_MAX];
};
extern "C" int xos_thread_runtime_init();
extern "C" void xos_cpp_tls_cleanup();
extern "C" void xos_thread_cleanup();
extern "C" int xos_thread_cleanup_active();
extern "C" [[noreturn]] void xos_thread_process_finish(int);
extern "C" xos_thread_control* xos_current_control();
extern "C" xos::i64 xos_allocate_thread(pthread_t*, void*(*)(void*), void*, size_t, bool);
