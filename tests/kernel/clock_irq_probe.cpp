// SPDX-License-Identifier: Apache-2.0
// Linked only with --clock-irq-probe. Never part of the default kernel.
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
u32 calls;
void callback(u8) { ++calls; }
void other_callback(u8) {}
bool check(bool value, const char* name) {
    format::text("[irq-audit] "); format::text(name);
    format::text(value ? " PASS\r\n" : " FAIL\r\n");
    return value;
}
}
bool clock_irq_probe() {
    using arch::in_byte;
    using arch::out_byte;
    bool ok = true;
    u64 flags;
    __asm__ volatile("pushfq; pop %0" : "=r"(flags));
    if (!check((flags & 0x200) == 0, "entry_IF_clear")) { return false; }
    const u64 before = clock::ticks();
    platform::pc::pic_eoi(0);
    platform::pc::pic_eoi(10);
    platform::device_irq(10); // Synthetic dispatch control, not a hardware NIC claim.
    ok = check(clock::ticks() == before, "EOI_and_device_dispatch_do_not_advance_time") && ok;
    const u8 master = in_byte(0x21), slave = in_byte(0xa1), elcr = in_byte(0x4d1);
    ok = check(platform::pc::claim_diagnostic_irq(10, callback), "exclusive_masked_route_claim") && ok;
    ok = check(!platform::pc::claim_diagnostic_irq(11, callback) &&
               !platform::pc::release_diagnostic_irq(10, other_callback), "duplicate_and_wrong_owner_denied") && ok;
    const u8 claimed_master = in_byte(0x21), claimed_slave = in_byte(0xa1);
    ok = check(claimed_master == (master & ~4u) && claimed_slave == (slave & ~4u) &&
               in_byte(0x4d1) == (elcr | 4u), "claim_only_owned_bits") && ok;
    platform::interrupts_init();
    ok = check(in_byte(0x21) == claimed_master && in_byte(0xa1) == claimed_slave &&
               clock::ticks() == before, "initialization_is_idempotent") && ok;
    const u32 previous = calls;
    platform::device_irq(11);
    platform::device_irq(10);
    ok = check(calls == previous + 1 && clock::ticks() == before, "selected_callback_only_no_clock_side_effect") && ok;
    // Change an unrelated ELCR bit while the lease is held; release must retain it.
    out_byte(0x4d1, static_cast<u8>(in_byte(0x4d1) ^ 2u));
    const u8 unrelated = in_byte(0x4d1) & 2u;
    ok = check(platform::pc::release_diagnostic_irq(10, callback) &&
               in_byte(0x21) == master && in_byte(0xa1) == slave &&
               (in_byte(0x4d1) & 4u) == (elcr & 4u) &&
               (in_byte(0x4d1) & 2u) == unrelated, "release_restores_owned_bits_preserves_other_owner") && ok;
    out_byte(0x4d1, elcr);
    ok = check(!platform::pc::release_diagnostic_irq(10, callback) &&
               !platform::pc::claim_diagnostic_irq(0, callback), "stale_release_and_timer_claim_denied") && ok;
    ok = check(platform::pc::claim_diagnostic_irq(10, callback), "second_route_claim") && ok;
    out_byte(0xa1, static_cast<u8>(in_byte(0xa1) & ~0x10u)); // Simulate input owning IRQ12.
    ok = check(platform::pc::release_diagnostic_irq(10, callback) &&
               in_byte(0xa1) == (slave & ~0x10u) && (in_byte(0x21) & 4u) == 0,
               "release_preserves_other_PIC_route_and_live_slave_cascade") && ok;
    out_byte(0xa1, slave); out_byte(0x21, master);
    const u64 pages = memory_status().free_pages;
    const u32 tasks = task_count();
    const u64 start = clock::ticks();
    while (clock::ticks() - start < 3) { arch::wait_for_interrupt(); }
    const u64 end = clock::ticks();
    ok = check(end >= start + 3 && clock::monotonic_ns() == end * clock::resolution_ns,
               "real_IRQ0_advances_single_clock_in_pre_run") && ok;
    ok = check(memory_status().free_pages == pages && task_count() == tasks && tasks == 8,
               "pre_run_IRQ0_does_not_schedule_or_allocate") && ok;
    format::text("[irq-audit] ticks="); format::decimal(end);
    format::text(" ns="); format::decimal(clock::monotonic_ns());
    format::text(" synthetic_device_entry_control=1\r\n");
    return ok;
}
}
