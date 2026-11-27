// SPDX-License-Identifier: Apache-2.0
#include "shared_cxx_exception.hpp"
#include <atomic>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <thread>
#include <utility>
#include <unistd.h>

namespace {
constexpr unsigned worker_value = 5;
thread_local unsigned application_value = 81;
thread_local unsigned application_zero;
std::atomic<unsigned> application_destroyed;
std::atomic<bool> started;
std::atomic<bool> finish;

struct holder {
    bool touched = false;

    ~holder() {
        if (touched && application_value == 81 + worker_value && application_zero == worker_value) {
            application_destroyed.fetch_add(1, std::memory_order_release);
            constexpr char marker[] = "D2_STD_THREAD_APP_TLS_DTOR\n";
            write(STDOUT_FILENO, marker, sizeof(marker) - 1);
        }
    }
};
thread_local holder application_holder;
}

int main() {
    const auto main_id = std::this_thread::get_id();
    const auto* main_value = &application_value;
    application_value = 97;
    application_zero = 53;

    std::thread worker([main_id, main_value] {
        if (std::this_thread::get_id() == main_id || &application_value == main_value
            || application_value != 81 || application_zero != 0
            || !exception_sample_init_worker_tls(worker_value)) {
            _Exit(55);
        }
        application_value += worker_value;
        application_zero = worker_value;
        application_holder.touched = true;
        try {
            throw_sample_error();
        } catch (const sample_error&) {
            if (exception_sample_state() != 101) {
                _Exit(56);
            }
        }
        errno = ERANGE;
        started.store(true, std::memory_order_release);
        while (!finish.load(std::memory_order_acquire)) {
            std::this_thread::yield();
        }
        if (errno != ERANGE || application_value != 81 + worker_value || application_zero != worker_value
            || !exception_sample_worker_tls_matches(worker_value)) {
            _Exit(57);
        }
    });
    errno = EDOM;
    while (!started.load(std::memory_order_acquire)) {
        std::this_thread::yield();
    }
    const auto worker_id = worker.get_id();
    std::thread joined(std::move(worker));
    if (worker.joinable() || !joined.joinable() || joined.get_id() != worker_id || worker_id == main_id
        || errno != EDOM || application_value != 97 || application_zero != 53 || exception_sample_state() != 0) {
        _Exit(58);
    }
    finish.store(true, std::memory_order_release);
    joined.join();
    if (joined.joinable() || joined.get_id() != std::thread::id{} || application_value != 97 || application_zero != 53
        || application_destroyed.load(std::memory_order_acquire) != 1 || exception_sample_destroyed() != 1) {
        return 59;
    }
    std::puts("D2_STD_THREAD_OK move=joined app-dtor=1 dso-dtor=1 tls=isolated");
    return 0;
}
