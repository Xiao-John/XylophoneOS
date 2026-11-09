// SPDX-License-Identifier: Apache-2.0
#include "src/kernel/core/vm_pin.hpp"
#include <cassert>
#include <cstdio>
int main() {
    xos::vm_pin pin{};
    assert(!pin.active() && !pin.set(1,0) && !pin.set(~xos::u64{0}-1,2));
    assert(pin.set(4094,8) && pin.active());
    assert(!pin.set(8192,1));
    assert(!pin.overlaps(0,4094) && pin.overlaps(4095,4096));
    assert(pin.overlaps(4096,8192) && !pin.overlaps(4102,8192));
    pin.clear(); assert(!pin.active() && !pin.overlaps(0,8192));
    std::puts("PASS bounded pin range and release");
}
