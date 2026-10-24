// SPDX-License-Identifier: Apache-2.0
#include <cstdio>
#include <typeinfo>

namespace {
struct base_type { virtual ~base_type() = default; };
struct derived_type final : base_type { int value = 91; };
}

int main() {
    derived_type derived;
    base_type* base = &derived;
    derived_type* result = dynamic_cast<derived_type*>(base);
    if (result == nullptr || result->value != 91 || typeid(*base) != typeid(derived_type)) {
        std::puts("[cpp_abi] rtti=fail");
        return 1;
    }
    std::puts("[cpp_abi] rtti=ok");
    return 0;
}
