// SPDX-License-Identifier: Apache-2.0
#include <cstdio>

namespace {
volatile int local_destroyed;

struct local_lifetime {
    ~local_lifetime() { local_destroyed = 1; }
};

__attribute__((noinline)) void throw_from_inner_frame() {
    local_lifetime guard;
    throw 73;
}

__attribute__((noinline)) void throw_from_outer_frame() {
    throw_from_inner_frame();
}
}

int main() {
    try {
        throw_from_outer_frame();
    } catch (int value) {
        if (value != 73 || local_destroyed != 1) {
            std::puts("[cpp_abi] exception_unwind=fail");
            return 1;
        }
        std::puts("[cpp_abi] exception_unwind=ok");
        return 0;
    }
    std::puts("[cpp_abi] exception_unwind=missing");
    return 2;
}
