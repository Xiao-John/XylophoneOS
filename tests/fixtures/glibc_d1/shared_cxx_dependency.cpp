// SPDX-License-Identifier: Apache-2.0
#include "shared_cxx_exception.hpp"
#include <unistd.h>

namespace {
int state;

struct holder {
    holder() { state += 1; }
    ~holder() {
        state += 10;
        static constexpr char message[] = "D2_SHARED_CXX_TLS_DTOR\n";
        if (state == 111) { write(STDOUT_FILENO, message, sizeof(message) - 1); }
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
