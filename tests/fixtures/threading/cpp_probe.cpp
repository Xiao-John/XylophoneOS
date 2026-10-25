// SPDX-License-Identifier: Apache-2.0
#include <thread>
#include <mutex>
#include <condition_variable>
#include <atomic>
#include <chrono>
#include <stdexcept>
#include <cstdio>
#include <cstdlib>
#include <xos/thread_core.hpp>
#ifndef _GLIBCXX_HAS_GTHREADS
#error This probe requires a rebuilt gthread-enabled C++ runtime
#endif
namespace {
std::mutex mutex;
std::condition_variable condition;
std::once_flag once;
std::atomic<unsigned> once_attempts{}, once_success{}, guards{}, tls_ended{};
unsigned count, ready;
void check(bool good, const char* label) {
    if (!good) { std::printf("[cppthread] FAIL %s\n", label); std::_Exit(92); }
}
struct tls_probe {
    unsigned id;
    ~tls_probe() { tls_ended.fetch_add(1); }
};
thread_local tls_probe local{99};
struct guarded {
    unsigned value;
    guarded() : value(42) {
        guards.fetch_add(1);
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
};
guarded& get_guarded() { static guarded value; return value; }
void worker(unsigned id) {
    check(local.id == 99, "TLS-init"); local.id = id;
    try {
        std::call_once(once, [] {
            if (once_attempts.fetch_add(1) == 0) { throw 17; }
            once_success.fetch_add(1);
        });
    } catch (int code) { check(code == 17, "once-exception"); }
    std::call_once(once, [] { once_attempts.fetch_add(1); once_success.fetch_add(1); });
    check(get_guarded().value == 42, "local-static");
    for (unsigned i = 0; i < 30; ++i) {
        try { throw std::runtime_error(id == 1 ? "one" : "two"); }
        catch (const std::runtime_error& error) {
            std::this_thread::yield(); // Keep simultaneous active EH states across a real switch.
            check(error.what()[0] == (id == 1 ? 'o' : 't') && local.id == id, "exception-state-isolation");
        }
        std::lock_guard<std::mutex> lock(mutex); ++count;
    }
    { std::lock_guard<std::mutex> lock(mutex); ++ready; }
    condition.notify_one();
}
}
int main(int argc, char**, char**) {
    if (argc > 1) { (void)std::chrono::system_clock::now(); return 95; }
    std::thread first(worker, 1), second(worker, 2);
    { std::unique_lock<std::mutex> lock(mutex); condition.wait(lock, [] { return ready == 2; }); }
    first.join(); second.join();
    check(count == 60 && guards == 1 && tls_ended == 2 && once_success == 1 && once_attempts == 2, "thread-join-once-guard-TLS");
    const auto start = std::chrono::steady_clock::now();
    {
        std::unique_lock<std::mutex> lock(mutex);
        check(condition.wait_for(lock, std::chrono::milliseconds(15)) == std::cv_status::timeout, "steady-cond-timeout");
    }
    check(std::chrono::steady_clock::now() - start >= std::chrono::milliseconds(15), "monotonic-chrono");
    std::printf("[cppthread] thread mutex cond once retry TLS exception guard chrono=ok\n");
    return 0;
}
