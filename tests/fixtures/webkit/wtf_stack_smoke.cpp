// SPDX-License-Identifier: Apache-2.0
#include "config.h"
#include <wtf/StackBounds.h>

#include <cstdio>
#include <pthread.h>

// Exercise the compiled private entry point without changing the upstream API.
WTF::StackBounds query_wtf_stack() asm("_ZN3WTF11StackBounds32currentThreadStackBoundsInternalEv");

namespace {

bool matches_attributes(pthread_t thread, const WTF::StackBounds& bounds) {
    pthread_attr_t attributes;
    if (pthread_getattr_np(thread, &attributes) != 0) {
        return false;
    }
    void* base = nullptr;
    size_t size = 0;
    const int bounds_error = pthread_attr_getstack(&attributes, &base, &size);
    const int destroy_error = pthread_attr_destroy(&attributes);
    if (bounds_error != 0 || destroy_error != 0) {
        return false;
    }

    return !bounds.isEmpty() && bounds.end() == base && bounds.size() == size;
}

bool check_current_stack() {
    auto bounds = query_wtf_stack();
    return bounds.contains(&bounds) && matches_attributes(pthread_self(), bounds);
}

struct worker_state {
    pthread_mutex_t entry = PTHREAD_MUTEX_INITIALIZER;
    bool stack_passed = false;
};

void* check_worker_stack(void* argument) {
    auto& state = *static_cast<worker_state*>(argument);
    if (pthread_mutex_lock(&state.entry) == 0) {
        const bool stack_passed = check_current_stack();
        state.stack_passed = pthread_mutex_unlock(&state.entry) == 0 && stack_passed;
    }
    return nullptr;
}

}

int main() {
    if (!check_current_stack()) {
        return 1;
    }

    worker_state state;
    pthread_t worker;
    if (pthread_mutex_lock(&state.entry) != 0
        || pthread_create(&worker, nullptr, check_worker_stack, &state) != 0) {
        return 2;
    }
    // Keep the worker in its entry handshake until the creator's query finishes.
    const auto peer_bounds = WTF::StackBounds::newThreadStackBounds(worker);
    const bool peer_passed = matches_attributes(worker, peer_bounds);
    if (pthread_mutex_unlock(&state.entry) != 0 || pthread_join(worker, nullptr) != 0
        || pthread_mutex_destroy(&state.entry) != 0 || !peer_passed || !state.stack_passed) {
        return 3;
    }

    std::puts("CLARKE_WTF_STACK_OK");
    return 0;
}
