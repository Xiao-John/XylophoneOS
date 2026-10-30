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
xos::u8 simulated_byte = 0;
}

namespace xos::sdk {
i64 syscall(u64 number, u64 first, u64, u64) {
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
    return 0;
}
}
namespace xos::thread {
i64 create(u64&, entry_function, void*, u64, bool) { return process_error_resources; }
}
namespace xos::user::uart {
i64 driver::start() { return 0; }
i64 driver::service_irq(u64) { return 0; }
i64 driver::read(u8* output, u32 length) {
    if (length == 0 || !has_byte) return 0;
    *output = simulated_byte; has_byte = false; return 1;
}
i64 driver::write(const u8*, u32 length) { return length != 0 && transmit_ready ? 1 : 0; }
i64 driver::arm_write() { return 0; }
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
    return 0;
}
