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
u64 waiting_irq;
u64 irq_waiter(void*) {
    __atomic_store_n(&phase, 1u, __ATOMIC_RELEASE);
    (void)thread::wake(&phase, 1);
    return static_cast<u64>(sdk::irq_event(irq_event_action::wait, waiting_irq, thread_deadline_infinite));
}
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
    if (sdk::equal(args[1], "irq_wait_close")) {
        const u8 line_control = 3, disabled = 0;
        __asm__ volatile("outb %0, %1" : : "a"(line_control), "Nd"(static_cast<u16>(0x3fb)));
        __asm__ volatile("outb %0, %1" : : "a"(disabled), "Nd"(static_cast<u16>(0x3f9)));
        const i64 token = sdk::irq_event(irq_event_action::bind, pio_resource_com1);
        if (token <= 0) return 25;
        waiting_irq = static_cast<u64>(token);
        u64 worker = 0;
        if (thread::create(worker, irq_waiter, nullptr) != 0) return 26;
        while (__atomic_load_n(&phase, __ATOMIC_ACQUIRE) == 0) (void)thread::wait(&phase, 0);
        const i64 now = sdk::syscall(sys_clock_monotonic);
        if (now < 0) return 27;
        const u64 deadline = static_cast<u64>(now) + 3000000000ull;
        for (;;) {
            thread_stats stats{};
            if (sdk::syscall(sys_thread_stats, reinterpret_cast<u64>(&stats)) != 0) return 28;
            if (stats.waiting != 0) break;
            if (sdk::syscall(sys_clock_monotonic) >= static_cast<i64>(deadline)) return 29;
            sdk::yield();
        }
        if (sdk::irq_event(irq_event_action::close, waiting_irq) != 0) return 30;
        u64 result = 0;
        if (thread::join(worker, result) != 0 || result != static_cast<u64>(process_error_denied) ||
            sdk::irq_event(irq_event_action::wait, waiting_irq, 0) != process_error_denied) return 31;
        return 0;
    }
    if (sdk::equal(args[1], "irq_delivery")) {
        const u8 line_control = 3, modem_control = 0x0b;
        __asm__ volatile("outb %0, %1" : : "a"(line_control), "Nd"(static_cast<u16>(0x3fb)));
        u8 ier = 0;
        __asm__ volatile("outb %0, %1" : : "a"(ier), "Nd"(static_cast<u16>(0x3f9)));
        __asm__ volatile("outb %0, %1" : : "a"(modem_control), "Nd"(static_cast<u16>(0x3fc)));
        const i64 token = sdk::irq_event(irq_event_action::bind, pio_resource_com1);
        if (token <= 0) return 21;
        ier = 2; // 16550 THRE interrupt, only enabled during this probe
        __asm__ volatile("outb %0, %1" : : "a"(ier), "Nd"(static_cast<u16>(0x3f9)));
        const i64 now = sdk::syscall(sys_clock_monotonic);
        if (now < 0) return 22;
        const u64 handle = static_cast<u64>(token);
        const i64 sequence = sdk::irq_event(irq_event_action::wait, handle,
                                            static_cast<u64>(now) + 3000000000ull);
        if (sequence <= 0 || sdk::irq_event(irq_event_action::wait, handle, 0) != sequence ||
            sdk::irq_event(irq_event_action::ack, handle, static_cast<u64>(sequence) + 1) != process_error_state)
            return 23;
        // Remove the device interrupt cause before acknowledging the event.
        ier = 0;
        __asm__ volatile("outb %0, %1" : : "a"(ier), "Nd"(static_cast<u16>(0x3f9)));
        if (sdk::irq_event(irq_event_action::ack, handle, static_cast<u64>(sequence)) != 0 ||
            sdk::irq_event(irq_event_action::ack, handle, static_cast<u64>(sequence)) != process_error_state ||
            sdk::irq_event(irq_event_action::wait, handle, 0) != process_error_would_block ||
            sdk::irq_event(irq_event_action::close, handle) != 0) return 24;
        return 0;
    }
    if (sdk::equal(args[1], "irq_empty")) {
        // Disable UART interrupt causes before binding; this test only checks
        // an empty IRQ source, not delivery of a real device interrupt.
        const u8 disabled = 0;
        __asm__ volatile("outb %0, %1" : : "a"(disabled), "Nd"(static_cast<u16>(0x3f9)));
        const i64 token = sdk::irq_event(irq_event_action::bind, pio_resource_com1);
        if (token <= 0 || sdk::irq_event(irq_event_action::bind, pio_resource_com1) != process_error_state)
            return 17;
        const u64 handle = static_cast<u64>(token);
        if (sdk::irq_event(irq_event_action::wait, handle, 0) != process_error_would_block ||
            sdk::irq_event(irq_event_action::ack, handle, 1) != process_error_state ||
            sdk::irq_event(irq_event_action::wait, handle + 1, 0) != process_error_denied) return 18;
        const i64 now = sdk::syscall(sys_clock_monotonic);
        if (now < 0 || sdk::irq_event(irq_event_action::wait, handle,
                static_cast<u64>(now) + 30000000ull) != thread_error_timeout) return 19;
        if (sdk::irq_event(irq_event_action::close, handle) != 0 ||
            sdk::irq_event(irq_event_action::wait, handle, 0) != process_error_denied ||
            sdk::irq_event(irq_event_action::ack, handle, 1) != process_error_denied ||
            sdk::irq_event(irq_event_action::bind, pio_resource_com1) != process_error_state) return 20;
        return 0;
    }
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
