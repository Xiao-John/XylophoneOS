// SPDX-License-Identifier: Apache-2.0
#include "abi_probe.hpp"
#include <cstdio>

int cpp_abi_b_saw_a;

namespace {
struct second_unit_lifetime {
    second_unit_lifetime() {
        cpp_abi_b_saw_a = cpp_abi_a_alive;
        std::puts("[cpp_abi] tu_b_ctor");
    }
    ~second_unit_lifetime() {
        std::puts(cpp_abi_a_alive ? "[cpp_abi] tu_b_dtor_order=ok" : "[cpp_abi] tu_b_dtor_order=fail");
    }
};

__attribute__((init_priority(300))) second_unit_lifetime second_unit_instance;
}
