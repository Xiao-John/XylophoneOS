// SPDX-License-Identifier: Apache-2.0
#include <xos/libc_runtime.hpp>
#ifdef XOS_THREADED_RUNTIME
#include <xos/thread_core.hpp>
#endif
#include <stdlib.h>
#include <stdint.h>
#include <sys/reent.h>

using init_function = void (*)();

extern "C" {
extern init_function __preinit_array_start[] __attribute__((weak));
extern init_function __preinit_array_end[] __attribute__((weak));
extern init_function __init_array_start[] __attribute__((weak));
extern init_function __init_array_end[] __attribute__((weak));
extern init_function __fini_array_start[] __attribute__((weak));
extern init_function __fini_array_end[] __attribute__((weak));
extern init_function __ctors_start[] __attribute__((weak));
extern init_function __ctors_end[] __attribute__((weak));
extern init_function __dtors_start[] __attribute__((weak));
extern init_function __dtors_end[] __attribute__((weak));
extern char __eh_frame_start[] __attribute__((weak));
void __register_frame(const void*) __attribute__((weak));
void __deregister_frame(const void*) __attribute__((weak));
void __call_exitprocs(int, void*);
[[noreturn]] void _exit(int);

// The XOS image is one static executable, so this object is its DSO identity.
void* __dso_handle = &__dso_handle;
}

namespace {
bool initialized;
bool eh_frame_registered;
struct tls_destructor {
    void (*function)(void*);
    void* object;
    tls_destructor* next;
};
#ifdef XOS_THREADED_RUNTIME
thread_local tls_destructor* tls_destructors;
thread_local bool draining_tls_destructors;
#else
tls_destructor* tls_destructors;
bool draining_tls_destructors;
#endif
bool exit_started;

void drain_tls_destructors() {
    if (draining_tls_destructors) { return; }
    draining_tls_destructors = true;
    while (tls_destructors != nullptr) {
        tls_destructor* current = tls_destructors;
        tls_destructors = current->next;
        void (*function)(void*) = current->function;
        void* object = current->object;
        free(current);
        function(object);
    }
    draining_tls_destructors = false;
}

bool valid_array(init_function* begin, init_function* end) {
    const uintptr_t first = reinterpret_cast<uintptr_t>(begin);
    const uintptr_t last = reinterpret_cast<uintptr_t>(end);
    return first != 0 && last >= first;
}

void run_forward(init_function* begin, init_function* end) {
    if (!valid_array(begin, end)) { return; }
    for (init_function* current = begin; current < end; ++current) {
        if (*current != nullptr) { (*current)(); }
    }
}

void run_reverse(init_function* begin, init_function* end) {
    if (!valid_array(begin, end)) { return; }
    while (end > begin) {
        --end;
        if (*end != nullptr) { (*end)(); }
    }
}

bool valid_legacy_function(init_function function) {
    const uintptr_t address = reinterpret_cast<uintptr_t>(function);
    return address != 0 && address != static_cast<uintptr_t>(-1);
}

void run_legacy_ctors_reverse(init_function* begin, init_function* end) {
    if (!valid_array(begin, end)) { return; }
    while (end > begin) {
        --end;
        if (valid_legacy_function(*end)) { (*end)(); }
    }
}

void run_legacy_dtors_forward(init_function* begin, init_function* end) {
    if (!valid_array(begin, end)) { return; }
    for (init_function* current = begin; current < end; ++current) {
        if (valid_legacy_function(*current)) { (*current)(); }
    }
}

void finish_cpp_runtime() {
    run_legacy_dtors_forward(__dtors_start, __dtors_end);
    run_reverse(__fini_array_start, __fini_array_end);
    if (eh_frame_registered && __deregister_frame != nullptr) {
        __deregister_frame(__eh_frame_start);
        eh_frame_registered = false;
    }
}
}

extern "C" int __cxa_thread_atexit(void (*function)(void*), void* object, void*) {
    if (function == nullptr) { return -1; }
    tls_destructor* entry = static_cast<tls_destructor*>(malloc(sizeof(tls_destructor)));
    if (entry == nullptr) { return -1; }
    entry->function = function;
    entry->object = object;
    entry->next = tls_destructors;
    tls_destructors = entry;
    return 0;
}

// Keep newlib's normal process-exit sequence, but run per-task TLS destructors
// before global atexit handlers. __call_exitprocs removes callbacks before
// invoking them and rescans handlers registered during callbacks.
#ifdef XOS_THREADED_RUNTIME
extern "C" void xos_thread_cleanup();
extern "C" int xos_thread_cleanup_active();
extern "C" void xos_cpp_tls_cleanup() { drain_tls_destructors(); }
extern "C" [[noreturn]] void xos_thread_process_finish(int status) {
    exit_started = true;
    do {
        __call_exitprocs(status, nullptr);
        drain_tls_destructors();
    } while (tls_destructors != nullptr);
    if (__stdio_exit_handler != nullptr) { __stdio_exit_handler(); }
    _exit(status);
}
#endif
extern "C" [[noreturn]] void exit(int status) {
#ifdef XOS_THREADED_RUNTIME
    if (exit_started || xos_thread_cleanup_active()) { _exit(status); }
    // Only this caller continues executing before any process-level callbacks.
    if (xos::sdk::syscall(xos::sys_process_begin_exit) != 0) { _exit(status); }
    if (exit_started) { _exit(status); }
    exit_started = true;
    xos_thread_cleanup();
    xos_thread_process_finish(status);
#else
    if (exit_started) { _exit(status); }
    exit_started = true;
    do {
        drain_tls_destructors();
        __call_exitprocs(status, nullptr);
    } while (tls_destructors != nullptr);
    if (__stdio_exit_handler != nullptr) { __stdio_exit_handler(); }
    _exit(status);
#endif
}

extern "C" int xos_cpp_runtime_init() {
    if (initialized) { return 0; }

    if (__eh_frame_start != nullptr && __register_frame != nullptr &&
        __deregister_frame != nullptr) {
        __register_frame(__eh_frame_start);
        eh_frame_registered = true;
    }

    // Register this first. Later C++ atexit handlers then run before fini arrays.
    if (atexit(finish_cpp_runtime) != 0) {
        if (eh_frame_registered) {
            __deregister_frame(__eh_frame_start);
            eh_frame_registered = false;
        }
        return -1;
    }

    // Set the guard before invoking user code in case a constructor re-enters.
    initialized = true;
    run_forward(__preinit_array_start, __preinit_array_end);
    run_forward(__init_array_start, __init_array_end);
    run_legacy_ctors_reverse(__ctors_start, __ctors_end);
    return 0;
}
