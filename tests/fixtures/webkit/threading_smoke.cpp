// SPDX-License-Identifier: Apache-2.0
#include "xos_stack_bounds.hpp"

#include <atomic>
#include <cerrno>
#include <cstdio>
#include <ctime>

namespace {

constexpr size_t worker_stack_size = 512 * 1024;
constexpr long ns_per_second = 1'000'000'000;
pthread_key_t thread_key;
std::atomic<int> destructor_calls{0};
std::atomic<int> destructor_error{0};

struct worker_state {
    pthread_mutex_t mutex = PTHREAD_MUTEX_INITIALIZER;
    pthread_cond_t condition = PTHREAD_COND_INITIALIZER;
    bool ready = false;
    bool release = false;
    int stack_error = 0;
    clarke::stack_bounds bounds{};
    std::uintptr_t stack_address = 0;
};

void destroy_tsd(void* value) {
    if (destructor_calls.fetch_add(1) == 0) {
        destructor_error = pthread_setspecific(thread_key, value);
    }
}

bool contains(const clarke::stack_bounds& bounds, std::uintptr_t address) {
    return bounds.low <= address && address < bounds.high;
}

int deadline_after(long delay_ns, timespec& deadline) {
    if (clock_gettime(CLOCK_REALTIME, &deadline) != 0) {
        return errno;
    }
    deadline.tv_sec += delay_ns / ns_per_second;
    deadline.tv_nsec += delay_ns % ns_per_second;
    if (deadline.tv_nsec >= ns_per_second) {
        ++deadline.tv_sec;
        deadline.tv_nsec -= ns_per_second;
    }
    return 0;
}

void* worker(void* argument) {
    auto& state = *static_cast<worker_state*>(argument);
    void* token = nullptr;
    if (pthread_setspecific(thread_key, argument) != 0 || pthread_getspecific(thread_key) != argument ||
        pthread_mutex_lock(&state.mutex) != 0) {
        return nullptr;
    }
    int on_stack = 0;
    state.stack_error = clarke::query_stack_bounds(pthread_self(), state.bounds);
    state.stack_address = reinterpret_cast<std::uintptr_t>(&on_stack);
    state.ready = true;
    const int signal_error = pthread_cond_signal(&state.condition);
    if (signal_error == 0) {
        timespec deadline;
        int error = deadline_after(4 * ns_per_second, deadline);
        while (error == 0 && !state.release) {
            error = pthread_cond_timedwait(&state.condition, &state.mutex, &deadline);
        }
        if (error == 0) {
            token = argument;
        }
    }
    return pthread_mutex_unlock(&state.mutex) == 0 ? token : nullptr;
}

}

#define CHECK(condition) do { \
    if (!(condition)) { \
        std::fprintf(stderr, "CLARKE_THREADING_FAIL line=%d %s\n", __LINE__, #condition); \
        return 1; \
    } \
} while (false)

int main() {
    int on_stack = 0;
    clarke::stack_bounds main_bounds{};
    CHECK(clarke::query_stack_bounds(pthread_self(), main_bounds) == 0);
    CHECK(contains(main_bounds, reinterpret_cast<std::uintptr_t>(&on_stack)));

    CHECK(pthread_key_create(&thread_key, destroy_tsd) == 0);
    worker_state state;
    pthread_attr_t attrs;
    CHECK(pthread_attr_init(&attrs) == 0);
    CHECK(pthread_attr_setstacksize(&attrs, worker_stack_size) == 0);
    CHECK(pthread_attr_setguardsize(&attrs, 4096) == 0);
    CHECK(pthread_mutex_lock(&state.mutex) == 0);
    pthread_t thread;
    CHECK(pthread_create(&thread, &attrs, worker, &state) == 0);
    CHECK(pthread_attr_destroy(&attrs) == 0);
    CHECK(!pthread_equal(pthread_self(), thread));
    timespec deadline;
    CHECK(deadline_after(4 * ns_per_second, deadline) == 0);
    while (!state.ready) {
        CHECK(pthread_cond_timedwait(&state.condition, &state.mutex, &deadline) == 0);
    }

    clarke::stack_bounds worker_bounds{};
    CHECK(state.stack_error == 0);
    CHECK(clarke::query_stack_bounds(thread, worker_bounds) == 0);
    CHECK(worker_bounds.low == state.bounds.low && worker_bounds.high == state.bounds.high);
    CHECK(worker_bounds.high - worker_bounds.low == worker_stack_size);
    CHECK(contains(worker_bounds, state.stack_address));
    CHECK(!contains(main_bounds, state.stack_address));
    CHECK(pthread_getspecific(thread_key) == nullptr);

    CHECK(deadline_after(20'000'000, deadline) == 0);
    int wait_status;
    do {
        wait_status = pthread_cond_timedwait(&state.condition, &state.mutex, &deadline);
    } while (wait_status == 0);
    CHECK(wait_status == ETIMEDOUT);
    timespec observed;
    CHECK(clock_gettime(CLOCK_REALTIME, &observed) == 0);
    CHECK(observed.tv_sec > deadline.tv_sec ||
          (observed.tv_sec == deadline.tv_sec && observed.tv_nsec >= deadline.tv_nsec));

    state.release = true;
    CHECK(pthread_cond_broadcast(&state.condition) == 0);
    CHECK(pthread_mutex_unlock(&state.mutex) == 0);
    void* result = nullptr;
    CHECK(pthread_join(thread, &result) == 0 && result == &state);
    CHECK(destructor_calls == 2 && destructor_error == 0);
    CHECK(pthread_key_delete(thread_key) == 0);
    CHECK(clarke::query_stack_bounds(thread, worker_bounds) == ESRCH);
    CHECK(worker_bounds.low == state.bounds.low && worker_bounds.high == state.bounds.high);
    CHECK(pthread_cond_destroy(&state.condition) == 0);
    CHECK(pthread_mutex_destroy(&state.mutex) == 0);
    std::puts("CLARKE_THREADING_OK");
    return 0;
}
