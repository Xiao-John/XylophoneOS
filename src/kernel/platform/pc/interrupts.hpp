// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/types.hpp>

namespace xos::platform::pc {
// PC PIC mechanisms, shared by timer/input/device dispatch. EOI is pure I/O.
void pic_eoi(u8 irq);
void pic_input_enable();
using diagnostic_irq_handler = void (*)(u8);
// Exactly one pre-run diagnostic consumer, only on an otherwise masked route.
// Callers enter and leave with IF=0. No runtime/shared PCI IRQ framework.
bool claim_diagnostic_irq(u8 irq, diagnostic_irq_handler handler);
bool release_diagnostic_irq(u8 irq, diagnostic_irq_handler handler);
}
