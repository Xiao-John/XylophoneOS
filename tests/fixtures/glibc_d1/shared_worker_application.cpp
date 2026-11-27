// SPDX-License-Identifier: Apache-2.0
#include "shared_cxx_exception.hpp"
#include <atomic>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <pthread.h>
#include <sched.h>
#include <typeinfo>

namespace {
constexpr unsigned capacity = 3;
constexpr unsigned last_id = 7;
constexpr uintptr_t initial_result = 0x62410000;
thread_local unsigned program_tls = 81;
std::atomic<unsigned> arrived;
std::atomic<bool> proceed;
pthread_t initial;

void run_exception(unsigned id) {
    if (program_tls != 81 || !exception_sample_init_worker_tls(id)) { _Exit(30); }
    program_tls += id;
    try {
        throw_sample_error();
    } catch (const std::runtime_error& error) {
        if (dynamic_cast<const sample_error*>(&error) == nullptr || typeid(error) != typeid(sample_error)
            || std::strcmp(error.what(), "the XOS shared C++ sample") != 0
            || exception_sample_state() != 101) { _Exit(31); }
    }
}

void* worker(void* argument) {
    const auto id = *static_cast<const unsigned*>(argument);
    run_exception(id);
    errno = static_cast<int>(100 + id);
    arrived.fetch_add(1, std::memory_order_release);
    while (!proceed.load(std::memory_order_acquire)) { sched_yield(); }
    if (errno != static_cast<int>(100 + id) || program_tls != 81 + id
        || !exception_sample_worker_tls_matches(id)) { _Exit(32); }
    return argument;
}

void check_last_tls() {
    if (pthread_equal(pthread_self(), initial) || program_tls != 81 + last_id
        || !exception_sample_worker_tls_matches(last_id) || exception_sample_state() != 111
        || exception_sample_destroyed() != 1) { _Exit(33); }
    std::puts("D2_SHARED_WORKER_LAST_ATEXIT tls=retained dtor=complete");
}

void* last_worker(void*) {
    void* status = nullptr;
    if (pthread_join(initial, &status) != 0 || reinterpret_cast<uintptr_t>(status) != initial_result) { _Exit(34); }
    run_exception(last_id);
    std::puts("D2_SHARED_WORKER_INITIAL_JOIN status=preserved");
    std::fflush(stdout);
    return nullptr;
}
}

int main() {
    initial = pthread_self();
    if (std::getenv("D2_WORKER_LAST") != nullptr) {
        pthread_t thread{};
        if (std::atexit(check_last_tls) != 0) { return 35; }
        const int error = pthread_create(&thread, nullptr, last_worker, nullptr);
        if (error != 0) {
            std::fprintf(stderr, "D2_SHARED_WORKER_LAST_CREATE_FAILED status=%d\n", error);
            return 35;
        }
        pthread_exit(reinterpret_cast<void*>(initial_result));
    }

    unsigned ids[] = {1, 2, 3, 4};
    pthread_t threads[capacity]{};
    for (unsigned i = 0; i < capacity; ++i) {
        const int error = pthread_create(&threads[i], nullptr, worker, &ids[i]);
        if (error != 0) {
            std::fprintf(stderr, "D2_SHARED_WORKER_CREATE_FAILED index=%u status=%d\n", i, error);
            return 36;
        }
    }
    while (arrived.load(std::memory_order_acquire) != capacity) { sched_yield(); }
    pthread_t refused{};
    if (pthread_create(&refused, nullptr, worker, &ids[3]) != EAGAIN || refused != 0) { return 37; }
    proceed.store(true, std::memory_order_release);
    for (unsigned i = 0; i < capacity; ++i) {
        void* result = nullptr;
        if (pthread_join(threads[i], &result) != 0 || result != &ids[i]) { return 38; }
    }
    pthread_t recycled{};
    const int recycle_error = pthread_create(&recycled, nullptr, worker, &ids[3]);
    if (recycle_error != 0) {
        std::fprintf(stderr, "D2_SHARED_WORKER_RECYCLE_FAILED status=%d\n", recycle_error);
        return 39;
    }
    void* result = nullptr;
    if (pthread_join(recycled, &result) != 0 || result != &ids[3] || exception_sample_destroyed() != 4
        || program_tls != 81 || exception_sample_state() != 0) { return 40; }
    std::puts("D2_SHARED_WORKERS_OK return=joined dtor=4 tls=isolated capacity=refused-and-reused");
    return 0;
}
