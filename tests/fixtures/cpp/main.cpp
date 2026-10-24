/* SPDX-License-Identifier: Apache-2.0 */
#include "state.hpp"
#include <string>
#include <vector>

extern int translation_unit_value();
extern int exception_unwind_probe();
extern int rtti_probe();
extern int tls_probe();
extern "C" int cpp_static_library_value();

namespace {
int local_constructions;
int local_static_value() {
    struct local_probe {
        int value;
        local_probe() : value(42) { ++local_constructions; }
    };
    static local_probe object;
    return object.value;
}
}

int main() {
    std::vector<int> values;
    values.push_back(translation_unit_value());
    std::string text("xos-seed");
    if (values.at(0) != 42 || text.size() != 8 || construction_count() != 1) return 1;
    if (exception_unwind_probe() != 3 || rtti_probe() != 7) return 2;
    if (tls_probe() != 0 || cpp_static_library_value() != 42) return 3;
    if (local_static_value() != 42 || local_static_value() != 42 || local_constructions != 1) return 4;
    return 0;
}
