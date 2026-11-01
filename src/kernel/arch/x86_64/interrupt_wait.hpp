// SPDX-License-Identifier: Apache-2.0
#pragma once
namespace xos::arch {
// Existing single-CPU lost-wakeup-safe IRQ wait, entered and resumed with IF=0.
inline void wait_for_interrupt() { __asm__ volatile("sti; hlt; cli" ::: "memory"); }
}
