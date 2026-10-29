// SPDX-License-Identifier: MIT AND Apache-2.0
// Historical MIT base; network IRQ additions 2026-10-29 are Apache-2.0.
#pragma once
#include <xos/types.hpp>

namespace xos::arch {
void pic_init();
void pic_input_enable();
void pic_eoi(u8 irq);
void pic_line_enable(u8 irq, bool enabled);
u64 pic_ticks();
void timer_init(u32 hz);
}
