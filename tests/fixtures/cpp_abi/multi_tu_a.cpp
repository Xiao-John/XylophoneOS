// SPDX-License-Identifier: Apache-2.0
#include "abi_probe.hpp"
#include <cstdio>

int cpp_abi_a_alive;

namespace {
struct first_unit_lifetime {
    first_unit_lifetime() { cpp_abi_a_alive = 1; std::puts("[cpp_abi] tu_a_ctor"); }
    ~first_unit_lifetime() { cpp_abi_a_alive = 0; std::puts("[cpp_abi] tu_a_dtor"); }
};

__attribute__((init_priority(200))) first_unit_lifetime first_unit_instance;
}
