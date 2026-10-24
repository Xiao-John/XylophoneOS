// SPDX-License-Identifier: Apache-2.0
#include <cstdio>

namespace {
int constructor_count;

struct local_value {
    local_value() : value(++constructor_count) {}
    int value;
};

local_value& get_local_value() {
    static local_value value;
    return value;
}
}

int main() {
    local_value* first = &get_local_value();
    local_value* second = &get_local_value();
    if (first != second || constructor_count != 1 || first->value != 1) {
        std::puts("[cpp_abi] local_static=fail");
        return 1;
    }
    std::puts("[cpp_abi] local_static=ok");
    return 0;
}
