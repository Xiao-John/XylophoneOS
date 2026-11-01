// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/types.hpp>

namespace xos::platform::pc {
// PC PIC mechanisms, shared by timer/input/device dispatch. EOI is pure I/O.
void pic_eoi(u8 irq);
void pic_input_enable();
}
