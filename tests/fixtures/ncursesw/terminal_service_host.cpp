// SPDX-License-Identifier: Apache-2.0
// Exercise the actual service wait path with a simulated in-process UART and
// wait-word implementation. This does not model the XOS kernel or hardware.
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <mutex>
#include <thread>
#include "../../../src/user/services/terminal.cpp"

namespace {
std::mutex wait_mutex;
std::condition_variable wait_changed;
std::atomic<unsigned> waits{0};
bool has_byte = false;
bool transmit_ready = false;
bool transmitter_idle = true;
unsigned sleeps = 0;
xos::u8 simulated_byte = 0;
xos::channel_info mock_channels[2]{};
xos::channel_fork_verification expected_fork{};
}

namespace xos::sdk {
i64 syscall(u64 number, u64 first, u64 second, u64 third) {
    if (number == sys_channel && first == static_cast<u64>(channel_action::verify_fork_pair)) {
        const auto& value = *reinterpret_cast<const channel_fork_verification*>(second);
        return value.version == expected_fork.version && value.size == expected_fork.size &&
               value.source_incoming == expected_fork.source_incoming &&
               value.source_outgoing == expected_fork.source_outgoing &&
               value.child_incoming == expected_fork.child_incoming &&
               value.child_outgoing == expected_fork.child_outgoing && value.child_pid == expected_fork.child_pid
            ? 0 : process_error_denied;
    }
    if (number == sys_channel && first == static_cast<u64>(channel_action::enumerate)) {
        if (second >= 2) return thread_error_not_found;
        *reinterpret_cast<channel_info*>(third) = mock_channels[second];
        return 0;
    }
    if (number == sys_wait_word) {
        const auto& request = *reinterpret_cast<const thread_wait_request*>(first);
        auto* address = reinterpret_cast<u32*>(request.address);
        std::unique_lock<std::mutex> guard(wait_mutex);
        ++waits;
        wait_changed.notify_all();
        if (__atomic_load_n(address, __ATOMIC_ACQUIRE) != request.expected) return thread_value_changed;
        if (request.deadline_ns == 0) return thread_error_timeout;
        const bool changed = wait_changed.wait_for(guard, std::chrono::seconds(2), [&] {
            return __atomic_load_n(address, __ATOMIC_ACQUIRE) != request.expected;
        });
        return changed ? 0 : thread_error_timeout;
    }
    if (number == sys_wake_word) { wait_changed.notify_all(); return 0; }
    if (number == sys_sleep_until) { ++sleeps; transmitter_idle = true; return 0; }
    return 0;
}
}
namespace xos::thread {
i64 create(u64&, entry_function, void*, u64, bool) { return process_error_resources; }
}
namespace xos::user::uart {
i64 driver::start() { return 0; }
i64 driver::service_irq(u64) { return 0; }
i64 driver::readable() const { return has_byte ? 1 : 0; }
i64 driver::read(u8* output, u32 length) {
    if (length == 0 || !has_byte) return 0;
    *output = simulated_byte; has_byte = false; return 1;
}
i64 driver::write(const u8*, u32 length) { return length != 0 && transmit_ready ? 1 : 0; }
i64 driver::arm_write() { return 0; }
i64 driver::transmitter_empty() { return transmitter_idle ? 1 : 0; }
i64 driver::flush_input() { has_byte = false; return 0; }
i64 driver::close() { return 0; }
}

int main() {
    using namespace xos;
    u8 output = 0;
    if (read_until(&output, 1, 0) != thread_error_timeout) return 1;
    const unsigned previous = waits.load();
    i64 result = 0;
    std::thread reader([&] { result = read_until(&output, 1, thread_deadline_infinite); });
    {
        std::unique_lock<std::mutex> guard(wait_mutex);
        if (!wait_changed.wait_for(guard, std::chrono::seconds(2), [&] { return waits.load() > previous; })) {
            guard.unlock(); reader.join(); return 2;
        }
    }
    {
        std::lock_guard<std::mutex> guard(wait_mutex);
        lock(); simulated_byte = 0xe4; has_byte = true;
        __atomic_store_n(&input_ready, 1u, __ATOMIC_RELEASE); unlock();
    }
    (void)thread::wake(&input_ready, 1);
    reader.join();
    if (result != 1 || output != 0xe4) return 3;
    const unsigned before_cancel = waits.load();
    std::thread cancelled([&] { result = read_until(&output, 1, thread_deadline_infinite); });
    {
        std::unique_lock<std::mutex> guard(wait_mutex);
        if (!wait_changed.wait_for(guard, std::chrono::seconds(2), [&] { return waits.load() > before_cancel; })) {
            guard.unlock(); cancelled.join(); return 4;
        }
        lock(); __atomic_store_n(&request_pending, 1u, __ATOMIC_RELEASE);
        __atomic_store_n(&input_ready, 1u, __ATOMIC_RELEASE); unlock();
    }
    (void)thread::wake(&input_ready, 1);
    cancelled.join();
    if (result != terminal::interrupted) return 5;
    lock(); __atomic_store_n(&request_pending, 0u, __ATOMIC_RELEASE); unlock();
    if (write_until(&output, 1, 0) != thread_error_timeout) return 6;
    const unsigned before_write = waits.load();
    std::thread writer([&] { result = write_until(&output, 1, thread_deadline_infinite); });
    {
        std::unique_lock<std::mutex> guard(wait_mutex);
        if (!wait_changed.wait_for(guard, std::chrono::seconds(2), [&] { return waits.load() > before_write; })) {
            guard.unlock(); writer.join(); return 7;
        }
        lock(); transmit_ready = true;
        __atomic_store_n(&input_ready, 1u, __ATOMIC_RELEASE); unlock();
    }
    (void)thread::wake(&input_ready, 1);
    writer.join();
    if (result != 1) return 8;
    controller_pid = 42;
    mock_channels[0] = {channel_version, sizeof(channel_info), 10, channel_receive, 7, 42};
    mock_channels[1] = {channel_version, sizeof(channel_info), 11, channel_send, 7, 42};
    const terminal::session_channels channels{10, 11, 7};
    if (!authenticated_app_channels(channels)) return 9;
    mock_channels[1].controller_pid = 41;
    if (authenticated_app_channels(channels)) return 10;
    mock_channels[1].controller_pid = 42; mock_channels[1].peer_pid = 8;
    if (authenticated_app_channels(channels)) return 11;
    mock_channels[1].peer_pid = 7; mock_channels[1].rights = channel_receive;
    if (authenticated_app_channels(channels)) return 12;
    auto mode = terminal::default_mode;
    if (!terminal::valid_mode(mode)) return 13;
    mode.vmin = 0; mode.vtime = 255;
    if (!terminal::valid_mode(mode)) return 14;
    mode.vmin = 2;
    if (terminal::valid_mode(mode)) return 15;
    mode = terminal::default_mode; mode.lflag = 1;
    if (terminal::valid_mode(mode)) return 16;
    app_mode = terminal::default_mode; app_mode.vmin = 0; app_mode.vtime = 0;
    if (read_configured(&output, 1) != 0) return 17;
    lock(); simulated_byte = 'X'; has_byte = true; unlock();
    if (read_configured(&output, 1) != 1 || output != 'X') return 18;
    transmitter_idle = false;
    if (drain_output() != 0 || sleeps != 1) return 19;
    __atomic_store_n(&request_pending, 1u, __ATOMIC_RELEASE);
    if (drain_output() != terminal::interrupted) return 20;
    __atomic_store_n(&request_pending, 0u, __ATOMIC_RELEASE);
    if (wait_readable(0) != thread_error_timeout) return 21;
    lock(); simulated_byte = 'Q'; has_byte = true; unlock();
    if (wait_readable(0) != 1 || wait_readable(0) != 1 ||
        read_until(&output, 1, 0) != 1 || output != 'Q') return 22;
    apps[0] = {10, 11, 7};
    expected_fork = {channel_version, sizeof(channel_fork_verification), 10, 11, 12, 13, 8};
    terminal::request admission{};
    admission.version = terminal::version; admission.size = sizeof(admission);
    admission.operation = static_cast<u32>(terminal::operation::fork_attach);
    admission.sequence = 1; admission.length = sizeof(terminal::session_channels);
    const terminal::session_channels child{12, 13, 8};
    const auto* child_bytes = reinterpret_cast<const u8*>(&child);
    for (u32 i = 0; i < sizeof(child); ++i) admission.data[i] = child_bytes[i];
    if (admit_fork(0, admission) != 0 || apps[1].incoming != 12 || apps[1].peer != 8) return 23;
    if (admit_fork(0, admission) != process_error_state) return 24;
    admission.data[0] = 99;
    if (admit_fork(0, admission) != process_error_denied || apps[2].incoming != 0) return 25;
    admission.length = 0;
    if (admit_fork(0, admission) != process_error_invalid) return 26;
    return 0;
}
