// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/types.hpp>

namespace xos::arch {
u64 execution_counter();
bool execution_clock_init();
u64 execution_time_ns(u64 cycles);
u64 execution_resolution_ns();
}
