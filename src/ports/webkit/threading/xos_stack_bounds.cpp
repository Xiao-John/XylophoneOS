// SPDX-License-Identifier: Apache-2.0
#include "xos_stack_bounds.hpp"

#include <cerrno>

namespace clarke {

int query_stack_bounds(pthread_t thread, stack_bounds& result) {
    pthread_attr_t attributes;
    const int query_error = pthread_getattr_np(thread, &attributes);
    if (query_error != 0) {
        return query_error;
    }

    void* base = nullptr;
    size_t size = 0;
    const int bounds_error = pthread_attr_getstack(&attributes, &base, &size);
    const int destroy_error = pthread_attr_destroy(&attributes);
    if (bounds_error != 0 || destroy_error != 0) {
        return bounds_error != 0 ? bounds_error : destroy_error;
    }
    if (base == nullptr || size == 0) {
        return EINVAL;
    }

    const auto low = reinterpret_cast<std::uintptr_t>(base);
    if (size > UINTPTR_MAX - low) {
        return EOVERFLOW;
    }
    result = {low, low + size};
    return 0;
}

}
