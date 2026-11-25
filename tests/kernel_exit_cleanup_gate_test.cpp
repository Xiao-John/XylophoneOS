// SPDX-License-Identifier: Apache-2.0
// Actual dispatch code is extracted from tasks.cpp by the Python runner.
// User-copy, time and peer reaping are deterministic stand-ins; timer expiry
// and real libc lock/cleanup behavior are qualified by the QEMU exit suite.
#include <xos/thread_abi.hpp>
#include <cstdio>
#include <cstdlib>

using namespace xos;
namespace clock { u64 monotonic_ns() { return 100; } }
enum class thread_state { free, runnable, dead };
enum class thread_wait_kind { none, other };
struct process_record {
    bool closing = false;
    u64 exit_owner = 0, exit_cleanup_deadline_ns = 0;
    i32 exit_cleanup_timeout_status = 0;
};
struct thread_record {
    process_record* process;
    u64 tid;
    thread_state state;
    thread_wait_kind wait_kind;
    bool detached;
};
process_record process;
process_record* current = &process;
thread_record threads[2];
thread_record* current_thread = &threads[0];
unsigned reap_calls;
void reap_threads() { ++reap_calls; }
template<class request>
i64 read_thread_request(u64 address, request& result) {
    result = *reinterpret_cast<const request*>(address);
    return 0;
}
#include "exit_cleanup_dispatch.inc"

void check(bool condition, const char* message) {
    if (!condition) { std::fprintf(stderr, "%s\n", message); std::exit(1); }
}
void reset() {
    process = {};
    threads[0] = {&process, 1, thread_state::runnable, thread_wait_kind::none, false};
    threads[1] = {&process, 2, thread_state::runnable, thread_wait_kind::other, false};
    current_thread = &threads[0];
    reap_calls = 0;
}
void bounded_unchanged(u64 deadline) {
    check(!process.closing && process.exit_owner == 1 && process.exit_cleanup_deadline_ns == deadline
          && process.exit_cleanup_timeout_status == 125, "bounded cleanup ownership/deadline changed");
    check(threads[1].state == thread_state::runnable && threads[1].wait_kind == thread_wait_kind::other
          && !threads[1].detached && reap_calls == 0, "bounded cleanup stopped or reaped peer");
}
int main() {
    reset();
    check(fork_admission_open(process), "ordinary process cannot fork");
    check(dispatch(0) == 0 && process.closing && process.exit_owner == 1,
          "first legacy stop-peers call changed");
    check(threads[1].state == thread_state::dead && threads[1].detached && reap_calls == 1,
          "legacy stop-peers no longer reaps peers");
    check(!fork_admission_open(process), "closing process retains fork admission");
    check(dispatch(0) == 0, "legacy owner reentry changed");
    reset();
    process_exit_cleanup_request request{{1, sizeof(request), 0}, 1000000100, 125, 0};
    check(dispatch(1, reinterpret_cast<u64>(&request)) == 0, "cleanup claim failed");
    const u64 deadline = request.deadline_ns;
    check(!fork_admission_open(process), "bounded cleanup retains fork admission");
    check(dispatch(0) == process_error_state, "cleanup owner downgraded to stop-peers");
    bounded_unchanged(deadline);
    current_thread = &threads[1];
    check(dispatch(0) == process_error_state, "cleanup peer stopped the owner");
    check(dispatch(1, reinterpret_cast<u64>(&request)) == thread_error_busy, "cleanup peer stole ownership");
    bounded_unchanged(deadline);
    current_thread = &threads[0];
    request.deadline_ns = 30000000100;
    request.timeout_status = 124;
    check(dispatch(1, reinterpret_cast<u64>(&request)) == 0, "cleanup owner reentry failed");
    bounded_unchanged(deadline);
    check(dispatch(0) == process_error_state, "repeated owner downgraded to stop-peers");
    bounded_unchanged(deadline);
    std::puts("PASS sys51 legacy behavior, bounded cleanup, and fork admission");
}
