// SPDX-License-Identifier: Apache-2.0
// Runs only under the dedicated supervisor's explicit COM1 grant.
#include <xos/sdk.hpp>
#include <xos/file_client.hpp>
#include <xos/channel_io.hpp>
#include <xos/thread_core.hpp>
using namespace xos;

namespace {
struct exec_marker { u64 magic; u32 version, size; };
[[gnu::section(".xos.exec"), gnu::used]] const exec_marker marker{exec_image_abi_magic, 3, sizeof(exec_marker)};
u32 phase;
u64 pio_worker(void*) {
    u8 value = 0;
    __asm__ volatile("inb %1, %0" : "=a"(value) : "Nd"(static_cast<u16>(0x3fd)));
    __atomic_store_n(&phase, 1u, __ATOMIC_RELEASE);
    (void)thread::wake(&phase, 1);
    while (__atomic_load_n(&phase, __ATOMIC_ACQUIRE) == 1)
        (void)thread::wait(&phase, 1);
    // The supervisor has revoked the whole process before waking this worker.
    __asm__ volatile("inb %1, %0" : "=a"(value) : "Nd"(static_cast<u16>(0x3fd)));
    return 14;
}
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
    if (sdk::equal(args[1], "revoke") || sdk::equal(args[1], "revoke_thread")) {
        const bool threaded = sdk::equal(args[1], "revoke_thread");
        channel_info first{}, second{};
        if (sdk::channel_get(0, first) != 0 || sdk::channel_get(1, second) != 0 ||
            first.rights == second.rights || first.peer_pid != second.peer_pid) return 11;
        const u32 send = first.rights == channel_send ? first.handle : second.handle;
        const u32 receive = first.rights == channel_receive ? first.handle : second.handle;
        u64 worker = 0;
        if (threaded) {
            if (thread::create(worker, pio_worker, nullptr) != 0) return 15;
            while (__atomic_load_n(&phase, __ATOMIC_ACQUIRE) == 0)
                (void)thread::wait(&phase, 0);
        }
        u8 value = 0;
        __asm__ volatile("inb %1, %0" : "=a"(value) : "Nd"(static_cast<u16>(0x3fd)));
        char byte = 'r';
        if (sdk::channel_send_wait(send, &byte, 1, thread_deadline_infinite) != 0 ||
            sdk::channel_receive_wait(receive, &byte, 1, thread_deadline_infinite) != 1 || byte != 'g' ||
            sdk::pio_grant(pio_grant_action::controller, 0, pio_resource_com1) != process_error_denied)
            return 12;
        if (threaded) {
            __atomic_store_n(&phase, 2u, __ATOMIC_RELEASE);
            (void)thread::wake(&phase, 1);
            u64 result = 0;
            (void)thread::join(worker, result);
            return 16; // the worker must fault the process before returning
        }
        __asm__ volatile("inb %1, %0" : "=a"(value) : "Nd"(static_cast<u16>(0x3fd)));
        return 13; // revoked access must fault
    }
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
