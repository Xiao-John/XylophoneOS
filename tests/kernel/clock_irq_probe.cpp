// SPDX-License-Identifier: Apache-2.0
// Test-only generic clock/IRQ audit; never linked into the default kernel.
#include <xos/clock.hpp>
#include <xos/platform.hpp>
#include <xos/format.hpp>
#include <xos/memory.hpp>
#include <xos/task.hpp>
#include "platform/pc/interrupts.hpp"
#include "arch/x86_64/io.hpp"
#include "arch/x86_64/interrupt_wait.hpp"

namespace xos {
namespace {
bool check(bool value, const char* name) {
    format::text("[irq-audit] ");
    format::text(name);
    format::text(value ? " PASS\r\n" : " FAIL\r\n");
    return value;
}
}

bool clock_irq_probe() {
    using arch::in_byte;
    bool ok = true;
    u64 flags;
    __asm__ volatile("pushfq; pop %0" : "=r"(flags));
    ok = check((flags & 0x200) == 0, "entry_IF_clear") && ok;

    const u64 before = clock::ticks();
    platform::pc::pic_eoi(0);
    platform::pc::pic_eoi(10);
    ok = check(clock::ticks() == before, "pure_EOI_does_not_advance_clock") && ok;

    const u8 master = in_byte(0x21), slave = in_byte(0xa1);
    platform::interrupts_init();
    ok = check(in_byte(0x21) == master && in_byte(0xa1) == slave &&
               clock::ticks() == before, "single_initialization_is_idempotent") && ok;

    const u64 pages = memory_status().free_pages;
    const u32 tasks = task_count();
    const u64 start = clock::ticks();
    while (clock::ticks() - start < 3) { arch::wait_for_interrupt(); }
    const u64 end = clock::ticks();
    ok = check(end >= start + 3 &&
               clock::monotonic_ns() == end * clock::resolution_ns,
               "IRQ0_advances_canonical_clock_before_run") && ok;
    ok = check(memory_status().free_pages == pages && task_count() == tasks && tasks == 8,
               "pre_run_IRQ0_does_not_schedule_or_allocate") && ok;
    format::text("[irq-audit] ticks="); format::decimal(end);
    format::text(" ns="); format::decimal(clock::monotonic_ns());
    format::text("\r\n");
    return ok;
}
}
