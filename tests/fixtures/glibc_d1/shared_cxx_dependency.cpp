// SPDX-License-Identifier: Apache-2.0
#include "shared_cxx_exception.hpp"
#include <atomic>
#include <unistd.h>

namespace {
thread_local int state;
thread_local unsigned template_value = 27;
thread_local unsigned zero_value;
std::atomic<unsigned> destroyed;

struct holder {
    holder() { state += 1; }
    ~holder() {
        state += 10;
        static constexpr char message[] = "D2_SHARED_CXX_TLS_DTOR\n";
        if (state == 111) {
            destroyed.fetch_add(1, std::memory_order_release);
            write(STDOUT_FILENO, message, sizeof(message) - 1);
        }
    }
};

struct unwind_guard {
    ~unwind_guard() { state += 100; }
};

thread_local holder local_holder;
}

sample_error::sample_error() : std::runtime_error("the XOS shared C++ sample") {}
sample_error::~sample_error() = default;

void throw_sample_error() {
    static_cast<void>(&local_holder);
    unwind_guard cleanup;
    throw sample_error{};
}

int exception_sample_state() { return state; }
unsigned exception_sample_destroyed() { return destroyed.load(std::memory_order_acquire); }

bool exception_sample_init_worker_tls(unsigned id) {
    if (template_value != 27 || zero_value != 0 || state != 0) { return false; }
    template_value += id;
    zero_value = id;
    return true;
}

bool exception_sample_worker_tls_matches(unsigned id) {
    return template_value == 27 + id && zero_value == id;
}
