// SPDX-License-Identifier: Apache-2.0
#include <xos/clock.hpp>

namespace xos::clock {
namespace {
// Single CPU, interrupt-serialized writer; reads must observe asynchronous IRQ0.
volatile u64 tick_count;
}
u64 ticks() { return tick_count; }
u64 monotonic_ns() {
    const u64 value = ticks();
    return value > (~u64{0} - 1) / resolution_ns
        ? ~u64{0} - 1 : value * resolution_ns;
}
void timer_interrupt() {
    const u64 value = tick_count;
    if (value != ~u64{0}) { tick_count = value + 1; }
}
}
