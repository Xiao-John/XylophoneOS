// SPDX-License-Identifier: Apache-2.0
#include <xos/thread_abi.hpp>

namespace {
using namespace xos;
struct alignas(16) test_tcb { u64 self, marker; };
test_tcb main_tcb{}, worker_tcb{};
alignas(16) const u64 readonly_tcb[2] = {0x13579, 0x24680};

i64 call(u64 number, u64 first = 0, u64 second = 0, u64 third = 0) {
    i64 result;
    __asm__ volatile("int $0x80" : "=a"(result)
                     : "a"(number), "D"(first), "S"(second), "d"(third) : "memory", "cc");
    return result;
}
u64 fs_self() {
    u64 value;
    __asm__ volatile("mov %%fs:0, %0" : "=r"(value) :: "memory");
    return value;
}
bool is_current(const test_tcb& tcb) {
    thread_info info{};
    return call(sys_thread_info, reinterpret_cast<u64>(&info)) == 0 &&
           info.thread_pointer == reinterpret_cast<u64>(&tcb) && fs_self() == tcb.self;
}
bool preempt_check(const test_tcb& tcb) {
    const i64 start = call(sys_clock_monotonic);
    if (start < 0) return false;
    for (;;) {
        if (!is_current(tcb)) return false;
        const i64 now = call(sys_clock_monotonic);
        if (now < start) return false;
        if (now - start >= 30000000) return true;
    }
}
i64 install(u64 pid, test_tcb& tcb) {
    tcb.self = reinterpret_cast<u64>(&tcb);
    return call(sys_process_tls, pid, tcb.self, static_cast<u64>(process_tls_mode::current_thread));
}
void message(const char* text, u64 size) { (void)call(sys_handle_write, 1, reinterpret_cast<u64>(text), size); }
int fail() {
    constexpr char text[] = "[tls-current] result=FAIL\n";
    message(text, sizeof(text) - 1);
    return 1;
}
}

extern "C" void worker_entry();

extern "C" xos::u64 worker_main(xos::u64 pid) {
    using namespace xos;
    worker_tcb.marker = 0xa55a;
    if (install(pid, worker_tcb) != 0 || !is_current(worker_tcb)) return 10;
    for (unsigned index = 0; index < 80; ++index) {
        (void)call(3);
        if (!is_current(worker_tcb)) return 11;
    }
    if (!preempt_check(worker_tcb)) return 15;
    // While the parent remains alive, begin_exit enters the non-last leaving
    // state. The only remaining legal operation is the final thread_exit.
    if (call(sys_thread_begin_exit) != 0) return 12;
    if (call(sys_process_tls, pid, reinterpret_cast<u64>(&main_tcb), 1) != process_error_state)
        return 13;
    return fs_self() == reinterpret_cast<u64>(&worker_tcb) ? 0 : 14;
}

extern "C" int probe_main() {
    using namespace xos;
    const i64 signed_pid = call(6);
    if (signed_pid <= 0) return fail();
    const u64 pid = static_cast<u64>(signed_pid);
    thread_header header{thread_abi_version, sizeof(thread_header), 0};
    if (call(sys_thread_profile, reinterpret_cast<u64>(&header)) != 0) return fail();
    if (call(sys_process_tls, pid, process_tls_begin) != process_error_denied) return fail();
    if (install(pid, main_tcb) != 0 || !is_current(main_tcb)) return fail();

    const u64 invalid[] = {0, 1, reinterpret_cast<u64>(&main_tcb) + 1,
        reinterpret_cast<u64>(readonly_tcb), process_heap_begin + 0x100000,
        process_user_begin - 16, process_user_end, ~u64{0} - 15};
    for (const u64 pointer : invalid) {
        if (call(sys_process_tls, pid, pointer, 1) != process_error_invalid ||
            !is_current(main_tcb)) return fail();
    }
    if (call(sys_process_tls, pid + 0x100000, main_tcb.self, 1) != process_error_denied ||
        !is_current(main_tcb)) return fail();
    if (call(sys_process_tls, pid, main_tcb.self, 2) != process_error_invalid ||
        !is_current(main_tcb)) return fail();
    if (call(sys_process_tls, pid, main_tcb.self, 0) != process_error_denied ||
        !is_current(main_tcb)) return fail();

    const char name[] = "tls_child";
    const i64 child = call(sys_process_create, 0, reinterpret_cast<u64>(name), sizeof(name) - 1);
    if (child <= 0) return fail();
    const i64 outside = call(sys_process_tls, static_cast<u64>(child), process_user_begin);
    const i64 unmapped = call(sys_process_tls, static_cast<u64>(child), process_tls_begin);
    const i64 foreign = call(sys_process_tls, static_cast<u64>(child), main_tcb.self, 1);
    const i64 aborted = call(sys_process_abort, static_cast<u64>(child));
    if (outside != process_error_invalid || unmapped != process_error_invalid ||
        foreign != process_error_denied || aborted != 0 || !is_current(main_tcb)) return fail();

    thread_prepare_request request{{thread_abi_version, sizeof(thread_prepare_request), 0},
                                  thread_stack_min, 4096, 0};
    thread_reservation reserved{};
    if (call(sys_thread_prepare, reinterpret_cast<u64>(&request), reinterpret_cast<u64>(&reserved)) != 0)
        return fail();
    auto* initial_tcb = reinterpret_cast<test_tcb*>(reserved.tls_begin);
    initial_tcb->self = reserved.tls_begin;
    initial_tcb->marker = 0;
    thread_start_request start{{thread_abi_version, sizeof(thread_start_request), 0},
        reserved.tid, reinterpret_cast<u64>(worker_entry), pid, reserved.stack_top, reserved.tls_begin};
    if (call(sys_thread_start, reinterpret_cast<u64>(&start)) != 0) {
        (void)call(sys_thread_abort, reserved.tid);
        return fail();
    }
    for (unsigned index = 0; index < 80; ++index) {
        (void)call(3);
        if (!is_current(main_tcb)) return fail();
    }
    if (!preempt_check(main_tcb)) return fail();
    u64 result = ~u64{0};
    if (call(sys_thread_join, reserved.tid, reinterpret_cast<u64>(&result)) != 0 || result != 0 ||
        !is_current(main_tcb)) return fail();
    constexpr char text[] = "[tls-current] result=pass invalid=8 identity=2 legacy=3 mode=1 threads=2 yields=160 preempt=2 leaving=1\n";
    message(text, sizeof(text) - 1);
    return 0;
}
