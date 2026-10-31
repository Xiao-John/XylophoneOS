// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/types.hpp>

namespace xos::clock {
inline constexpr u64 resolution_ns = 10000000;
u64 ticks();
u64 monotonic_ns();
// Internal IRQ0 writer, not an SDK interface. No other path advances time.
void timer_interrupt();
}
