// SPDX-License-Identifier: Apache-2.0
// Runs only under the dedicated supervisor's explicit COM1 grant.
#include <xos/sdk.hpp>
#include <xos/file_client.hpp>
using namespace xos;

namespace {
struct exec_marker { u64 magic; u32 version, size; };
[[gnu::section(".xos.exec"), gnu::used]] const exec_marker marker{exec_image_abi_magic, 3, sizeof(exec_marker)};
}

extern "C" int xos_user_main(const startup_info* startup) {
    if (startup->argc != 2) return 1;
    const auto args = reinterpret_cast<const char* const*>(startup->argv);
    if (sdk::equal(args[1], "after_exec")) {
        u8 value = 0;
        __asm__ volatile("inb %1, %0" : "=a"(value) : "Nd"(static_cast<u16>(0x3fd)));
        return 4;
    }
    if (sdk::pio_grant(pio_grant_action::controller, 0, pio_resource_com1) <= 0) return 2;
    if (sdk::equal(args[1], "exec") || sdk::equal(args[1], "badexec")) {
        const bool missing = sdk::equal(args[1], "badexec");
        sdk::spawn_options options{}; options.replace_image = true;
        const char* replacement[] = {"/bin/pio_auth.elf", "after_exec"};
        const i64 result = sdk::spawn_file_options(missing ? "/missing" : replacement[0], 2, replacement, options);
        if (!missing || result >= 0 || sdk::pio_grant(pio_grant_action::controller, 0, pio_resource_com1) <= 0)
            return 5;
        u8 value = 0;
        __asm__ volatile("inb %1, %0" : "=a"(value) : "Nd"(static_cast<u16>(0x3fd)));
        return 0;
    }
    if (sdk::equal(args[1], "fork")) {
        const i64 child = sdk::syscall(sys_process_fork_prepare);
        if (child == 0) {
            u8 value = 0;
            __asm__ volatile("inb %1, %0" : "=a"(value) : "Nd"(static_cast<u16>(0x3fd)));
            return 6;
        }
        if (child < 0) return 7;
        file::Client files{};
        if (!files.init()) return 8;
        i64 cloned = static_cast<i64>(file::status::would_block);
        for (u32 attempt = 0; attempt < 128 && cloned == static_cast<i64>(file::status::would_block); ++attempt) {
            cloned = files.clone_session(static_cast<u64>(child));
            if (cloned == static_cast<i64>(file::status::would_block)) sdk::yield();
        }
        if (cloned != 0 || sdk::syscall(sys_process_fork_commit, static_cast<u64>(child)) != 0) {
            (void)sdk::syscall(sys_process_abort, static_cast<u64>(child)); return 9;
        }
        process_status status{};
        if (sdk::wait(static_cast<u64>(child), status) != 0 || status.outcome != process_outcome::faulted ||
            status.vector != 13 || sdk::pio_grant(pio_grant_action::controller, 0, pio_resource_com1) <= 0)
            return 10;
        u8 value = 0;
        __asm__ volatile("inb %1, %0" : "=a"(value) : "Nd"(static_cast<u16>(0x3fd)));
        return 0;
    }
    if (sdk::equal(args[1], "inside")) {
        u8 line = 0, scratch = 0;
        __asm__ volatile("inb %1, %0" : "=a"(line) : "Nd"(static_cast<u16>(0x3fd)));
        __asm__ volatile("inb %1, %0" : "=a"(scratch) : "Nd"(static_cast<u16>(0x3ff)));
        (void)line; (void)scratch;
        return 0;
    }
    if (sdk::equal(args[1], "below")) {
        u8 value = 0;
        __asm__ volatile("inb %1, %0" : "=a"(value) : "Nd"(static_cast<u16>(0x3f7)));
    } else if (sdk::equal(args[1], "above")) {
        u8 value = 0;
        __asm__ volatile("inb %1, %0" : "=a"(value) : "Nd"(static_cast<u16>(0x400)));
    } else if (sdk::equal(args[1], "cross")) {
        u16 value = 0;
        __asm__ volatile("inw %1, %0" : "=a"(value) : "Nd"(static_cast<u16>(0x3ff)));
    } else return 3;
    return 4; // access outside the granted range must fault before this point
}
