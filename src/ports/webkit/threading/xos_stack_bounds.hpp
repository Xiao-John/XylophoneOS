// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <cstdint>
#include <pthread.h>

namespace clarke {

struct stack_bounds {
    std::uintptr_t low;
    std::uintptr_t high;
};

// Queries the accessible, half-open glibc stack range for a live XOS thread.
// The result is unchanged on failure. A caller observing a peer must hold
// that peer's lifetime through any use of the returned bounds.
int query_stack_bounds(pthread_t thread, stack_bounds& result);

}
