// SPDX-License-Identifier: MIT AND Apache-2.0
// Historical MIT base; XOS changes from 2026-10-24 are Apache-2.0.
#include <xos/console.hpp>
#include <xos/fault.hpp>
#include <xos/format.hpp>
#include <xos/memory.hpp>
#include <xos/platform.hpp>
#include <xos/task.hpp>
#include <xos/virtio_gpu.hpp>
#include "build_info.hpp"

namespace xos {
#if XOS_CLOCK_IRQ_PROBE
bool clock_irq_probe();
#endif
namespace {
constexpr usize line_capacity = 64;
char line[line_capacity];
usize line_length;
bool line_overflow;
u64 last_allocated;
bool have_last_allocated;
#if XOS_EASTER_EGGS
u32 joke_index;
#endif

bool equals(const char* left, const char* right) {
    while (*left != '\0' && *left == *right) {
        ++left;
        ++right;
    }
    return *left == *right;
}

void command_help() {
#if XOS_EASTER_EGGS
    format::text("help mem alloc free vmtest run pf gp ud div df halt guo joke about\r\n");
#else
    format::text("help mem alloc free vmtest run pf gp ud div df halt\r\n");
#endif
}

#if XOS_EASTER_EGGS
void command_guo() {
    format::text("[guo] name=\"Guo YePeng\" role=\"friend, chaos consultant\"\r\n");
    format::text("[guo] status=did_not_panic_yet ego=+1\r\n");
    format::text("[guo] tip=if it breaks, check the GDT first\r\n");
}

void command_joke() {
    static const char* const jokes[] = {
        "Why did the page fault cross the road? It had a valid CR2.",
        "Two hard things in OSDev: naming things, cache invalidation, and off-by-one errors.",
        "Guo YePeng asked for one tiny feature. The roadmap gained an E-number.",
        "64-bit kernel, 8-bit jokes. The jokes are not paged in.",
        "This kernel enforces W^X. The jokes are write-only.",
    };
    constexpr u32 joke_count = 5;
    format::text("[joke] ");
    format::text(jokes[joke_index % joke_count]);
    format::text("\r\n");
    ++joke_index;
}

void command_about() {
    format::text("XOS E07 | x86-64 | NASM + restricted C++ | build=" XOS_BUILD_ID "\r\n");
    format::text("Not Linux, not trying to be. Guo YePeng is in the credits; "
                 "the bugs are still mine.\r\n");
}

void print_easter_egg_banner() {
    format::text("\r\n"
                 "  ================================================\r\n"
                 "   XOS 0.0.2 | 64-bit | more checks than excuses\r\n"
                 "   Guest star: Guo YePeng (did not panic, yet)\r\n"
                 "   \"It booted on my machine.\" - everyone, ever\r\n"
                 "  ================================================\r\n"
                 "   guo = ceremonial greeting    joke = deterministic\r\n"
                 "   help = actual work\r\n");
}
#endif

void command_mem() {
    const memory_stats stats = memory_status();
    format::text("[mem] usable_kib=");
    format::decimal(stats.usable_bytes / 1024);
    format::text(" managed_kib=");
    format::decimal(stats.managed_bytes / 1024);
    format::text(" pages=");
    format::decimal(stats.total_pages);
    format::text(" free=");
    format::decimal(stats.free_pages);
    format::text(" allocated=");
    format::decimal(stats.allocated_pages);
    format::text("\r\n[mem] window=");
    format::hex(stats.low_address);
    format::text("..");
    format::hex(stats.high_address);
    format::text("\r\n");
}

void command_alloc() {
    u64 physical = 0;
    const memory_result result = allocate_page(&physical);
    format::text("alloc result=");
    format::text(memory_result_name(result));
    if (result == memory_result::none) {
        last_allocated = physical;
        have_last_allocated = true;
        format::text(" phys=");
        format::hex(physical);
    }
    format::text("\r\n");
}

void command_free() {
    if (!have_last_allocated) {
        format::text("free result=invalid\r\n");
        return;
    }
    const memory_result result = release_page(last_allocated);
    format::text("free result=");
    format::text(memory_result_name(result));
    format::text("\r\n");
    if (result == memory_result::none) {
        have_last_allocated = false;
        last_allocated = 0;
    }
}

void command_vmtest() {
    const bool ok = memory_self_check();
    format::text("vmtest result=");
    format::text(ok ? "pass" : "fail");
    format::text("\r\n");
}

void execute() {
    line[line_length] = '\0';
    if (line_length == 0) { return; }
    if (equals(line, "help")) { command_help(); }
    else if (equals(line, "mem")) { command_mem(); }
    else if (equals(line, "alloc")) { command_alloc(); }
    else if (equals(line, "free")) { command_free(); }
    else if (equals(line, "vmtest")) { command_vmtest(); }
#if XOS_CLOCK_IRQ_PROBE
    else if (equals(line, "irq-audit")) { format::text(clock_irq_probe()?"irq-audit pass\r\n":"irq-audit FAIL\r\n"); }
#endif

    else if (equals(line, "gpu-quota-test")) {format::text(virtio_gpu::resource_limit_test()?"gpu-quota-test pass\r\n":"gpu-quota-test unavailable_or_failed\r\n");}
    else if (equals(line, "gpu-test")) {format::text(virtio_gpu::self_test()?"gpu-test pass\r\n":"gpu-test unavailable_or_failed\r\n");}
    else if (equals(line, "run")) {
        format::text("[sched] event=starting\r\n");
        tasks_start();
    }
    else if (equals(line, "pf")) { trigger_fault(fault_trigger::page_fault); }
    else if (equals(line, "gp")) { trigger_fault(fault_trigger::general_protection); }
    else if (equals(line, "ud")) { trigger_fault(fault_trigger::invalid_opcode); }
    else if (equals(line, "div")) { trigger_fault(fault_trigger::divide_error); }
    else if (equals(line, "df")) { trigger_fault(fault_trigger::double_fault); }
    else if (equals(line, "halt")) {
        format::text("HALTED: CPU resting; close QEMU to exit.\r\n");
        arch::halt();
    }
#if XOS_EASTER_EGGS
    else if (equals(line, "guo")) { command_guo(); }
    else if (equals(line, "joke")) { command_joke(); }
    else if (equals(line, "about")) { command_about(); }
#endif
    else { format::text("ERROR: unknown_command\r\n"); }
}
}

[[noreturn]] void run_console() {
#if XOS_EASTER_EGGS
    print_easter_egg_banner();
#endif
    format::text("xos64> ");
    for (;;) {
        const int value = platform::debug_read();
        if (value < 0) { continue; }
        const char received = static_cast<char>(value);
        if (received == '\r' || received == '\n') {
            format::text("\r\n");
            if (line_overflow) {
                format::text("ERROR: line_too_long\r\n");
            } else {
                execute();
            }
            line_length = 0;
            line_overflow = false;
            format::text("xos64> ");
        } else if (received == '\b' || received == static_cast<char>(0x7f)) {
            if (line_length > 0) {
                --line_length;
                format::text("\b \b");
            }
        } else if (received >= ' ' && received <= '~') {
            if (line_length + 1 < line_capacity) {
                line[line_length++] = received;
                const char echo[2] = {received, '\0'};
                format::text(echo);
            } else {
                line_overflow = true;
            }
        }
    }
}
}
