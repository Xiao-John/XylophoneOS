// SPDX-License-Identifier: Apache-2.0
#include <cstdio>

namespace {
struct tls_value {
    tls_value() : value(0x584f53) { std::puts("[cpp_abi] tls_ctor"); }
    ~tls_value() { std::puts("[cpp_abi] tls_dtor_normal_exit"); }
    int value;
};

thread_local tls_value worker_value;
}

int main() {
    if (worker_value.value != 0x584f53) {
        std::puts("[cpp_abi] tls_value=fail");
        return 1;
    }
    std::puts("[cpp_abi] tls_before_normal_exit");
    return 0;
}
