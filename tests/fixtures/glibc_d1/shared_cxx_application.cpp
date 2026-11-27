// SPDX-License-Identifier: Apache-2.0
#include "shared_cxx_exception.hpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <typeinfo>

namespace {
void check_tls_teardown() {
    if (exception_sample_state() != 111) { _Exit(20); }
    std::puts("D2_SHARED_CXX_ATEXIT");
}

}

int main() {
    if (exception_sample_state() != 0 || std::atexit(check_tls_teardown) != 0) { return 10; }
    try {
        throw_sample_error();
    } catch (const std::runtime_error& error) {
        if (dynamic_cast<const sample_error*>(&error) == nullptr || typeid(error) != typeid(sample_error)
            || std::strcmp(error.what(), "the XOS shared C++ sample") != 0
            || exception_sample_state() != 101) { return 11; }
    }
    std::puts("D2_SHARED_CXX_OK throw=DSO catch=PIE rtti=shared unwind=complete");
    std::fflush(stdout);
    return 0;
}
