// SPDX-License-Identifier: Apache-2.0
#include "xos_stack_bounds.hpp"

#include <array>
#include <atomic>
#include <condition_variable>
#include <cstdio>
#include <functional>
#include <mutex>
#include <stdexcept>
#include <thread>

namespace {
bool global_ready;
std::atomic<unsigned> worker_destructors{};

struct startup_marker {
    startup_marker() {
        global_ready = true;
        std::puts("GLIBC_UNIFIED_GLOBAL_CTOR");
    }
} startup;

struct tls_slot {
    unsigned value = 7;
    bool main_thread = false;

    ~tls_slot() {
        if (main_thread) {
            std::puts("GLIBC_UNIFIED_MAIN_TLS_DTOR");
        } else {
            worker_destructors.fetch_add(1, std::memory_order_relaxed);
        }
    }
};
thread_local tls_slot slot;

struct scope_marker {
    unsigned& destructors;
    ~scope_marker() { ++destructors; }
};

__attribute__((noinline)) void throw_across_frame(unsigned& destructors) {
    scope_marker guard{destructors};
    throw std::runtime_error("unified sdk unwind");
}

bool native_stack_contains(const void* local) {
    clarke::stack_bounds bounds{};
    const auto address = reinterpret_cast<std::uintptr_t>(local);
    return clarke::query_stack_bounds(pthread_self(), bounds) == 0
        && bounds.low <= address && address < bounds.high;
}

struct worker_result {
    std::uintptr_t tls_address = 0;
    bool passed = false;
};

struct worker_start {
    std::mutex lock;
    std::condition_variable signal;
    unsigned count = 0;
    bool released = false;
};

void run_worker(worker_start& start, worker_result& result, unsigned value) {
    bool initial = slot.value == 7;
    slot.value = value;
    result.tls_address = reinterpret_cast<std::uintptr_t>(&slot);
    {
        std::unique_lock lock(start.lock);
        ++start.count;
        start.signal.notify_all();
        start.signal.wait(lock, [&] { return start.released; });
    }

    unsigned destructors = 0;
    try {
        throw_across_frame(destructors);
    } catch (const std::runtime_error&) {
        result.passed = initial && slot.value == value && destructors == 1
            && native_stack_contains(&destructors);
    }
}
}

int main() {
    if (!global_ready || slot.value != 7) {
        return 1;
    }
    int stack_marker = 0;
    if (!native_stack_contains(&stack_marker)) {
        return 2;
    }
    slot.main_thread = true;
    slot.value = 73;
    worker_start start;
    std::array<worker_result, 2> results{};
    std::thread first(run_worker, std::ref(start), std::ref(results[0]), 11);
    std::thread second(run_worker, std::ref(start), std::ref(results[1]), 13);
    {
        std::unique_lock lock(start.lock);
        start.signal.wait(lock, [&] { return start.count == results.size(); });
        start.released = true;
        start.signal.notify_all();
    }
    first.join();
    second.join();
    const auto main_address = reinterpret_cast<std::uintptr_t>(&slot);
    if (!results[0].passed || !results[1].passed || slot.value != 73
        || results[0].tls_address == results[1].tls_address
        || results[0].tls_address == main_address || results[1].tls_address == main_address
        || worker_destructors.load(std::memory_order_relaxed) != results.size()) {
        return 3;
    }
    std::puts("GLIBC_UNIFIED_CXX_THREADS_TLS_UNWIND_STACK_PASS");
    return 0;
}
