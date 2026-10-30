#pragma once
#include <xos/types.hpp>

namespace xos::arch {
void pic_init();
void pic_input_enable();
void pic_mask_irq(u8 irq);
void pic_unmask_irq(u8 irq);
void pic_eoi(u8 irq);
void timer_init(u32 hz);
}
