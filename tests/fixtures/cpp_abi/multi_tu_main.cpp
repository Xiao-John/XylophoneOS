// SPDX-License-Identifier: Apache-2.0
#include "abi_probe.hpp"
#include <cstdio>

int main() {
    if (cpp_abi_a_alive != 1 || cpp_abi_b_saw_a != 1) {
        std::puts("[cpp_abi] multi_tu_init=fail");
        return 1;
    }
    std::puts("[cpp_abi] multi_tu_init=ok");
    std::puts("[cpp_abi] multi_tu_exit_expected=tu_b_dtor_order=ok,tu_a_dtor");
    return 0;
}
