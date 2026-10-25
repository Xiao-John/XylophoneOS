// SPDX-License-Identifier: Apache-2.0
// Real pthread + newlib read/write/close, including in-flight object leases.
#include <pthread.h>
#include <xos/thread_core.hpp>
#include <unistd.h>
#include <errno.h>
#include <string.h>

using namespace xos;
namespace {
constexpr u64 second = 1000000000ull;
u32 finished;

void check(bool value, const char* label) {
    if (value) return;
    sdk::print("C1_PTHREAD_FAIL "); sdk::print(label); sdk::print("\n");
    sdk::exit(92);
}
thread_stats stats() {
    thread_stats value{};
    check(sdk::syscall(sys_thread_stats, reinterpret_cast<u64>(&value)) == 0, "stats");
    return value;
}
void counters(const char* label, const thread_stats& value) {
    sdk::print("C1_PTHREAD_COUNTERS "); sdk::print(label);
    sdk::print(" free="); sdk::decimal(value.free_pages);
    sdk::print(" processes="); sdk::decimal(value.processes);
    sdk::print(" threads="); sdk::decimal(value.threads);
    sdk::print(" reserved="); sdk::decimal(value.reserved);
    sdk::print(" waiting="); sdk::decimal(value.waiting);
    sdk::print(" results="); sdk::decimal(value.results);
    sdk::print(" user_pages="); sdk::decimal(value.process_user_pages);
    sdk::print(" kernel_stack_pages="); sdk::decimal(value.process_kernel_stack_pages);
    sdk::print("\n");
}
void same_resources(const thread_stats& baseline, const char* label) {
    const auto current = stats();
    counters(label, current);
    check(current.free_pages == baseline.free_pages && current.processes == baseline.processes &&
          current.threads == baseline.threads && current.reserved == baseline.reserved &&
          current.waiting == baseline.waiting && current.results == baseline.results &&
          current.process_user_pages == baseline.process_user_pages &&
          current.process_kernel_stack_pages == baseline.process_kernel_stack_pages, label);
}
void* watchdog(void*) {
    const u64 deadline = thread::clock() + 12 * second;
    while (__atomic_load_n(&finished, __ATOMIC_ACQUIRE) == 0) {
        const i64 result = thread::wait(&finished, 0, deadline);
        if (__atomic_load_n(&finished, __ATOMIC_ACQUIRE) != 0) break;
        if (result == thread_error_timeout) {
            sdk::print("C1_PTHREAD_TIMEOUT\n"); sdk::exit(93);
        }
        check(result == 0 || result == thread_value_changed, "watchdog-wait");
    }
    return nullptr;
}
struct io_context {
    int fd;
    bool writing;
    u32 progress;
    ssize_t result;
    int error;
    unsigned char data[64];
};
void* io_worker(void* raw) {
    auto& context = *static_cast<io_context*>(raw);
    __atomic_store_n(&context.progress, 1u, __ATOMIC_RELEASE);
    context.result = context.writing ? write(context.fd, context.data, sizeof(context.data))
                                    : read(context.fd, context.data, 1);
    context.error = errno;
    __atomic_store_n(&context.progress, 2u, __ATOMIC_RELEASE);
    return &context;
}
pthread_t start(io_context& context) {
    pthread_t tid;
    check(pthread_create(&tid, nullptr, io_worker, &context) == 0, "worker-create");
    return tid;
}
void join(pthread_t tid, io_context& context, ssize_t expected) {
    void* value = nullptr;
    check(pthread_join(tid, &value) == 0 && value == &context, "worker-join");
    check(__atomic_load_n(&context.progress, __ATOMIC_ACQUIRE) == 2 && context.result == expected,
          "worker-result");
}
void await_waiting(u32 count, io_context* context = nullptr) {
    const u64 deadline = thread::clock() + second;
    for (;;) {
        if (stats().waiting == count && (!context ||
            __atomic_load_n(&context->progress, __ATOMIC_ACQUIRE) == 1)) return;
        check(thread::clock() < deadline, "expected-blocked-count-and-progress");
        check(thread::sleep_until(thread::clock() + thread_tick_ns) == 0, "observe-sleep");
    }
}
void close_pair(const int* pair) {
    check(close(pair[0]) == 0 && close(pair[1]) == 0, "close-pair");
}
void read_wake(const thread_stats& baseline) {
    int pair[2]; check(pipe(pair) == 0, "read-pipe");
    io_context reader{}; reader.fd = pair[0];
    const auto tid = start(reader);
    await_waiting(2, &reader);
    const unsigned char token = 0x43;
    check(write(pair[1], &token, 1) == 1, "read-wake-write");
    join(tid, reader, 1);
    check(reader.data[0] == token, "read-wake-byte");
    close_pair(pair);
    same_resources(baseline, "read_wake_end");
    sdk::print("C1_PTHREAD blocked_read_write_wake=ok\n");
}
void full_wake(const thread_stats& baseline) {
    int pair[2]; check(pipe(pair) == 0, "full-pipe");
    unsigned char data[process_pipe_bytes]; memset(data, 0x21, sizeof(data));
    check(write(pair[1], data, sizeof(data)) == sizeof(data), "fill-pipe");
    io_context writer{}; writer.fd = pair[1]; writer.writing = true;
    memset(writer.data, 0x7b, sizeof(writer.data));
    const auto tid = start(writer);
    await_waiting(2, &writer);
    check(read(pair[0], data, 257) == 257, "full-release-space");
    join(tid, writer, sizeof(writer.data));
    check(close(pair[1]) == 0, "full-close-writer");
    unsigned count = 0;
    for (;;) {
        const auto amount = read(pair[0], data, sizeof(data));
        check(amount >= 0, "full-drain-read");
        if (!amount) break;
        for (ssize_t i = 0; i < amount; ++i, ++count)
            check(data[i] == (count < process_pipe_bytes - 257 ? 0x21 : 0x7b), "full-drain-byte");
    }
    check(count == process_pipe_bytes - 257 + sizeof(writer.data), "full-drain-count");
    check(close(pair[0]) == 0, "full-close-reader");
    same_resources(baseline, "full_wake_end");
    sdk::print("C1_PTHREAD blocked_full_write_read_wake=ok\n");
}
void close_and_reuse(const thread_stats& baseline) {
    int original[2]; check(pipe(original) == 0, "lease-pipe");
    io_context reader{}; reader.fd = original[0];
    const auto tid = start(reader);
    await_waiting(2, &reader);
    // close removes the descriptor but the blocked read pins its open object.
    check(close(original[0]) == 0, "close-in-flight-read-fd");
    await_waiting(2, &reader);
    int replacement[2]; check(pipe(replacement) == 0, "replacement-pipe");
    check(replacement[0] == original[0], "same-numeric-fd-reused");
    const unsigned char replacement_byte = 0xb6, original_byte = 0xa5;
    unsigned char received = 0;
    check(write(replacement[1], &replacement_byte, 1) == 1 &&
          read(replacement[0], &received, 1) == 1 && received == replacement_byte,
          "replacement-object-independent");
    await_waiting(2, &reader);
    check(write(original[1], &original_byte, 1) == 1, "original-object-still-pinned");
    join(tid, reader, 1);
    check(reader.data[0] == original_byte, "in-flight-target-not-rebound");
    check(close(original[1]) == 0, "lease-close-original-writer");
    close_pair(replacement);
    same_resources(baseline, "close_reuse_end");
    sdk::print("C1_PTHREAD close_keeps_inflight_lease numeric_fd_reuse_isolated=ok\n");
}
void close_eof(const thread_stats& baseline) {
    int pair[2]; check(pipe(pair) == 0, "eof-pipe");
    io_context reader{}; reader.fd = pair[0];
    const auto tid = start(reader);
    await_waiting(2, &reader);
    check(close(pair[1]) == 0, "close-last-writer");
    join(tid, reader, 0);
    check(close(pair[0]) == 0, "eof-close-reader");
    same_resources(baseline, "eof_end");
    sdk::print("C1_PTHREAD close_last_writer_wakes_blocked_libc_read_eof=ok\n");
}
void* warmup(void*) { return nullptr; }
}
int main() {
    // Warm runtime initialization before recording exact page counts.
    pthread_t warm[2];
    check(pthread_create(&warm[0], nullptr, warmup, nullptr) == 0 &&
          pthread_create(&warm[1], nullptr, warmup, nullptr) == 0, "warmup-create");
    check(pthread_join(warm[0], nullptr) == 0 && pthread_join(warm[1], nullptr) == 0, "warmup-join");
    const auto initial = stats(); counters("initial", initial);
    pthread_t alarm;
    check(pthread_create(&alarm, nullptr, watchdog, nullptr) == 0, "watchdog-create");
    await_waiting(1);
    const auto steady = stats(); counters("steady_with_watchdog", steady);
    read_wake(steady);
    full_wake(steady);
    close_and_reuse(steady);
    close_eof(steady);
    __atomic_store_n(&finished, 1u, __ATOMIC_RELEASE);
    check(thread::wake(&finished) == 1, "watchdog-wake");
    check(pthread_join(alarm, nullptr) == 0, "watchdog-join");
    same_resources(initial, "final");
    sdk::print("C1_PTHREAD resources=baseline PASS\n");
    return 0;
}
