// SPDX-License-Identifier: Apache-2.0
#include "wake_gate.hpp"
#include <pthread.h>
#include <cstdio>
#include <cstdint>
#include <time.h>

static xos_wake_gate gate;
static unsigned stage;
static unsigned observed_waiting;
static void *worker(void *) {
    while (__atomic_load_n(&stage, __ATOMIC_ACQUIRE) == 0) { }
    timespec pause{0, 30000000};
    nanosleep(&pause, nullptr);
    xos::thread_stats stats{};
    if (xos::sdk::syscall(xos::sys_thread_stats, reinterpret_cast<xos::u64>(&stats)) == 0)
        observed_waiting = stats.waiting;
    gate.wake();
    __atomic_store_n(&stage, 2u, __ATOMIC_RELEASE);
    return nullptr;
}
struct RaceContext { xos_wake_gate *gate; long delay; };
static void *race_worker(void *raw) {
    auto *ctx = static_cast<RaceContext *>(raw);
    timespec delay{0, ctx->delay};
    nanosleep(&delay, nullptr);
    ctx->gate->wake();
    return nullptr;
}
int main() {
    if (xos::thread::enable() != 0) return 1;
    if (xos::thread::wait(reinterpret_cast<xos::u32 *>(1), 0, xos::thread::clock() + 100000000ULL) != xos::thread_error_address) return 28;
    if (gate.wake() < 0) return 2;
    if (gate.wait(xos::thread::clock() + 1000000000ULL) != xos::thread_value_changed) return 3;
    if (!gate.take()) return 27;
    const auto start = xos::thread::clock();
    auto result = gate.wait(start + 50000000ULL);
    const auto end = xos::thread::clock();
    if (result != xos::thread_error_timeout || end < start + 50000000ULL) return 4;
    pthread_t t;
    if (pthread_create(&t, nullptr, worker, nullptr) != 0) return 5;
    __atomic_store_n(&stage, 1u, __ATOMIC_RELEASE);
    result = gate.wait(xos::thread::clock() + 2000000000ULL);
    if (result != 0 && result != xos::thread_value_changed) return 6;
    if (pthread_join(t, nullptr) != 0 || __atomic_load_n(&stage, __ATOMIC_ACQUIRE) != 2) return 7;
    if (observed_waiting == 0) return 8;
    for (int i = 0; i < 9; ++i) {
        xos_wake_gate local;
        RaceContext context{&local, long((1 + i % 3) * 10000000)};
        pthread_t racing;
        if (pthread_create(&racing, nullptr, race_worker, &context) != 0) return 9;
        const auto deadline = xos::thread::clock() + 20000000ULL;
        auto status = local.wait(deadline);
        auto after = xos::thread::clock();
        if (status != 0 && status != xos::thread_value_changed && status != xos::thread_error_timeout) return 10;
        if (status == xos::thread_error_timeout && after < deadline) return 11;
        if (pthread_join(racing, nullptr) != 0 || !local.pending()) return 12;
    }
    std::puts("QT_WAKE_GATE_OK wake-before-wait timeout pthread-wake blocked-state race invalid-address destroy-joined");
    return 0;
}
