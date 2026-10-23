#include <xos/boot_info.hpp>
#include <xos/console.hpp>
#include <xos/fault.hpp>
#include <xos/format.hpp>
#include <xos/memory.hpp>
#include <xos/platform.hpp>
#include <xos/task.hpp>
#include <xos/block.hpp>
#include "build_info.hpp"

namespace {
volatile xos::u64 bss_probe[512];
volatile xos::u64 data_probe = 0x584f535f44415441;
}

extern "C" [[noreturn]] void kernel_main(const xos::boot_info* info,
                                         const xos::memory_region* regions) {
    xos::platform::debug_init();
    xos::format::text("[boot] event=kernel_enter arch=");
    xos::format::text(xos::arch::name());
    xos::format::text(" build=" XOS_BUILD_ID "\r\n");
    if (info == nullptr ||
        xos::validate_boot_info(*info, regions) != xos::boot_error::none) {
        xos::format::text("[boot] result=failed reason=invalid_boot_info\r\n");
        xos::arch::halt();
    }
    for (xos::usize i = 0; i < 512; ++i) {
        if (bss_probe[i] != 0) {
            xos::format::text("[boot] result=failed reason=bss_not_zero\r\n");
            xos::arch::halt();
        }
    }
    if (data_probe != 0x584f535f44415441) {
        xos::format::text("[boot] result=failed reason=data_corrupt\r\n");
        xos::arch::halt();
    }
    xos::format::text("[boot] event=boot_info_valid memory_map=complete\r\n");
    xos::format::text("[boot] event=runtime_checked bss=zero data=valid\r\n");

    xos::arch::exceptions_init();
    xos::format::text("[cpu] event=exceptions_ready idt=");
    xos::format::hex(xos::arch::exception_idt_address());
    xos::format::text(" vectors=32 double_fault_ist=1\r\n");

    xos::arch::paging_init(*info, regions);
    xos::memory_init(*info, regions);
    const xos::memory_stats stats = xos::memory_status();
    xos::format::text("[mem] event=initialized usable_kib=");
    xos::format::decimal(stats.usable_bytes / 1024);
    xos::format::text(" managed_kib=");
    xos::format::decimal(stats.managed_bytes / 1024);
    xos::format::text(" pages=");
    xos::format::decimal(stats.total_pages);
    xos::format::text(" free_pages=");
    xos::format::decimal(stats.free_pages);
    xos::format::text(" allocated_pages=");
    xos::format::decimal(stats.allocated_pages);
    xos::format::text("\r\n[mem] event=window low=");
    xos::format::hex(stats.low_address);
    xos::format::text(" high=");
    xos::format::hex(stats.high_address);
    xos::format::text("\r\n");

    if (!xos::memory_self_check()) {
        xos::format::text("[boot] result=failed reason=memory_self_check\r\n");
        xos::arch::halt();
    }
    if (xos::block::init()) {
        xos::format::text("[block] event=ready device=ata sectors=");
        xos::format::decimal(xos::block::sector_count());
        xos::format::text("\r\n");
    } else {
        xos::format::text("[block] event=absent device=ata\r\n");
    }
    if (!xos::tasks_init()) {
        xos::format::text("[boot] result=failed reason=tasks_init\r\n");
        xos::arch::halt();
    }

    xos::format::text("[boot] result=ready stage=E04\r\n");
#if XOS_EASTER_EGGS
    xos::format::text("The underscores made it to 64 bits.\r\n");
#endif
    xos::run_console();
}
