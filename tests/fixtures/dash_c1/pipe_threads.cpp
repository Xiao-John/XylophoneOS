// SPDX-License-Identifier: Apache-2.0
// Mechanism-only guest probe. No newlib/pthread calls from worker threads.
#include <xos/thread_core.hpp>

using namespace xos;
namespace {
constexpr u64 second = 1000000000ull;
u32 finished;
u8 buffer[process_pipe_bytes];

void check(bool good, const char* name) {
    if (good) { return; }
    sdk::print("C1_THREADS_FAIL "); sdk::print(name); sdk::print("\n");
    sdk::exit(90);
}
thread_stats stats() {
    thread_stats value{};
    check(sdk::syscall(sys_thread_stats, reinterpret_cast<u64>(&value)) == 0, "stats");
    return value;
}
pipe_handles new_pipe() {
    pipe_handles value{};
    check(sdk::syscall(sys_pipe_create, reinterpret_cast<u64>(&value)) == 0, "pipe-create");
    return value;
}
void close_token(u32 token) { check(sdk::syscall(sys_pipe_close, token) == 0, "pipe-close"); }
i64 read_pipe(u32 token, u64 length = 1) {
    return sdk::syscall(sys_pipe_read, token, reinterpret_cast<u64>(buffer), length);
}
i64 write_pipe(u32 token, u64 length = 1) {
    return sdk::syscall(sys_pipe_write, token, reinterpret_cast<u64>(buffer), length);
}
u64 watchdog(void*) {
    const u64 deadline = thread::clock() + 12 * second;
    while (__atomic_load_n(&finished, __ATOMIC_ACQUIRE) == 0) {
        const i64 result = thread::wait(&finished, 0, deadline);
        if (result == thread_error_timeout && __atomic_load_n(&finished, __ATOMIC_ACQUIRE) == 0) {
            sdk::print("C1_THREADS_TIMEOUT\n"); sdk::exit(91);
        }
        if (__atomic_load_n(&finished, __ATOMIC_ACQUIRE) != 0) { return 0; }
        check(result == 0 || result == thread_value_changed, "watchdog-wait");
    }
    return 0;
}
struct wait_context {
    u32 token;
    // If a token was closed during the wait, readiness wakes the thread but
    // cannot confer a new handle. The actual I/O must revalidate ownership.
    bool closed;
    bool writable;
};
u64 pipe_waiter(void* raw) {
    auto& context = *static_cast<wait_context*>(raw);
    check(sdk::syscall(sys_pipe_wait, context.token) == 0, "pipe-wait-return");
    if (context.closed) {
        const i64 result = context.writable ? write_pipe(context.token) : read_pipe(context.token);
        check(result == process_error_denied, "closed-token-io-denied");
        check(sdk::syscall(sys_pipe_wait, context.token) == process_error_denied,
              "closed-token-wait-denied");
    }
    return 77;
}
u64 start_waiter(wait_context& context) {
    u64 tid = 0;
    check(thread::create(tid, pipe_waiter, &context, thread_stack_min) == 0, "waiter-create");
    return tid;
}
void join_waiter(u64 tid) {
    u64 value = 0;
    check(thread::join(tid, value) == 0 && value == 77, "waiter-join");
}
void await_waiting(u32 count) {
    const u64 deadline = thread::clock() + second;
    while (stats().waiting != count) {
        check(thread::clock() < deadline, "expected-blocked-count");
        check(thread::sleep_until(thread::clock() + thread_tick_ns) == 0, "observe-sleep");
    }
}
void close_alias(bool writable) {
    const auto pair = new_pipe();
    // Keep the same-direction reference alive in an unstarted child. No child
    // ELF, scheduling, file RPC, or busy polling is required for this case.
    const i64 child = sdk::syscall(sys_process_create, 0);
    check(child > 0, "alias-child-create-requires-driver");
    const u32 token = writable ? pair.write_token : pair.read_token;
    check(sdk::syscall(sys_process_stdio, static_cast<u64>(child), writable ? 1 : 0, token) == 0,
          "alias-child-stdio");
    if (writable) { check(write_pipe(pair.write_token, sizeof(buffer)) == sizeof(buffer), "alias-fill"); }
    wait_context context{token, true, writable};
    const u64 tid = start_waiter(context);
    await_waiting(2); // watchdog plus pipe waiter
    close_token(token);
    join_waiter(tid);
    check(sdk::syscall(sys_process_abort, static_cast<u64>(child)) == 0, "alias-child-abort");
    close_token(writable ? pair.read_token : pair.write_token);
}
}

extern "C" int xos_user_main(const startup_info*) {
    check(thread::enable() == 0, "thread-profile");
    const auto baseline = stats();
    u64 alarm = 0;
    check(thread::create(alarm, watchdog, nullptr, thread_stack_min) == 0, "watchdog-create");
    await_waiting(1);

    auto pair = new_pipe();
    wait_context empty{pair.read_token, false, false};
    const u64 first = start_waiter(empty), other = start_waiter(empty);
    await_waiting(3); // both readers must actually be asleep before the write
    check(write_pipe(pair.write_token) == 1, "wake-two-readers-write");
    join_waiter(first); join_waiter(other);
    check(read_pipe(pair.read_token) == 1, "read-wakeup-byte");
    sdk::print("C1_THREADS two_empty_read_waiters=ok\n");

    check(write_pipe(pair.write_token, sizeof(buffer)) == sizeof(buffer), "fill-capacity");
    check(write_pipe(pair.write_token) == process_error_would_block, "full-write-EAGAIN");
    wait_context full{pair.write_token, false, true};
    const u64 writer = start_waiter(full);
    await_waiting(2);
    check(read_pipe(pair.read_token) == 1, "full-read-releases-space");
    join_waiter(writer);
    check(write_pipe(pair.write_token) == 1, "write-after-wake");
    check(read_pipe(pair.read_token, sizeof(buffer)) == sizeof(buffer), "drain-full-pipe");
    sdk::print("C1_THREADS full_write_wait_read_wake=ok\n");

    // Exercise either side of the check/enqueue race. A write before the
    // worker enters sys_pipe_wait must be observed as immediately ready;
    // a write after it blocks must wake it. join is a real blocking syscall.
    for (u32 round = 0; round < 64; ++round) {
        if (round & 1) { check(write_pipe(pair.write_token) == 1, "prewrite"); }
        const u64 tid = start_waiter(empty);
        if (!(round & 1)) { check(write_pipe(pair.write_token) == 1, "racing-write"); }
        join_waiter(tid);
        check(read_pipe(pair.read_token) == 1, "race-byte");
    }
    sdk::print("C1_THREADS check_enqueue_race_rounds=64 preexisting_readiness=ok\n");

    const u64 eof_waiter = start_waiter(empty);
    await_waiting(2);
    close_token(pair.write_token);
    join_waiter(eof_waiter);
    check(read_pipe(pair.read_token) == 0, "last-writer-EOF");
    close_token(pair.read_token);

    pair = new_pipe();
    check(write_pipe(pair.write_token, sizeof(buffer)) == sizeof(buffer), "broken-fill");
    full.token = pair.write_token;
    const u64 broken_waiter = start_waiter(full);
    await_waiting(2);
    close_token(pair.read_token);
    join_waiter(broken_waiter);
    check(write_pipe(pair.write_token) == pipe_error_broken, "last-reader-EPIPE");
    close_token(pair.write_token);
    sdk::print("C1_THREADS close_last_writer_eof=ok close_last_reader_epipe=ok\n");

    close_alias(false); close_alias(true);
    sdk::print("C1_THREADS close_wait_token_with_same_direction_alias=ok\n");
    __atomic_store_n(&finished, 1u, __ATOMIC_RELEASE);
    check(thread::wake(&finished) == 1, "watchdog-wake");
    u64 value = 1;
    check(thread::join(alarm, value) == 0 && value == 0, "watchdog-join");
    const auto final = stats();
    check(final.free_pages == baseline.free_pages && final.threads == baseline.threads &&
          final.processes == baseline.processes && final.results == baseline.results &&
          final.process_user_pages == baseline.process_user_pages &&
          final.process_kernel_stack_pages == baseline.process_kernel_stack_pages,
          "thread-process-page-baseline");
    sdk::print("C1_THREADS resources=baseline PASS\n");
    return 0;
}
