// SPDX-License-Identifier: Apache-2.0
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <initializer_list>
#include <sys/mman.h>
#include <xos/memory.hpp>
#include <xos/audio_abi.hpp>
#include <xos/ipc_v1_abi.hpp>
#include <xos/device_abi.hpp>
#include <xos/format.hpp>
#include "core/thread_lifecycle.hpp"
#include "core/stream_lease.hpp"
#include "core/vm_pin.hpp"
#include "core/vm_continuation.hpp"
#include "core/user_copyout.hpp"
#include "core/cpu_accounting.hpp"
#include "arch/x86_64/frame.hpp"

namespace xos {
bool host_write_allowed = true;
memory_result query_page(u64 address, u64* physical, page_permissions* permissions) {
    if (address < process_user_begin || address >= process_user_begin + 3 * page_size) {
        return memory_result::not_mapped;
    }
    *physical = address;
    *permissions = {host_write_allowed, false, true};
    return memory_result::none;
}
memory_result inspect_user_write_in(u64, u64 address, user_write_page& page) {
    page = {};
    if (!host_write_allowed) return memory_result::not_mapped;
    u64 physical;
    page_permissions permissions{};
    return query_page(address, &physical, &permissions);
}
memory_result stage_user_write(user_write_page&) { std::abort(); }
bool user_write_unchanged_in(u64, const user_write_page&) { std::abort(); }
void publish_user_write_in(u64, user_write_page&) { std::abort(); }
memory_result release_user_page(u64) { std::abort(); }
}
namespace xos::platform {
bool debug_write(const char*) { return true; }
}
#if XOS_IPC_DEADLINES
namespace xos::clock {
u64 host_now;
u64 monotonic_ns() { return host_now; }
}
#endif
namespace xos::arch {
[[noreturn]] void halt() { std::abort(); }
u64 execution_counter() { return 0; }
namespace {
#include "kernel_wait_records.inc"
process_record tasks[8];
thread_record threads[thread_max_total];
endpoint_record endpoints[max_endpoints];
u64 files_pid;
#if XOS_IPC_DEADLINES
ipc_connection_record ipc_connections[16];
ipc_v1_call_record ipc_v1_calls[ipc_v1_max_pending_calls];
#endif
process_record* current;
thread_record* current_thread;
cpu_accounting cpu_usage;
bool reap_pending[8];
constexpr bool process_trace_enabled = false;
stream_lease input_lease;
u32 schedules;

// Device and display teardown are outside this process-wait test. The Files
// reply wake path below uses the extracted production IPC wake implementation.
void ipc_v1_revoke_process(u64) {}
void device_revoke_process(u64) {}
void release_pc_speaker(process_record*) {}
void revoke_pc_speaker_controller(process_record*) {}
void quarantine_com1(process_record*) {}
void release_channels(u64) {}
void display_release(u64) {}
void* schedule(interrupt_frame* frame) { ++schedules; return frame; }
void finish_task(process_record*, process_outcome, i64, u64 = 0, u64 = 0, u64 = 0);
void wake_ipc_waiters(u32, i64, thread_wait_kind = thread_wait_kind::none);

#include "kernel_wait_implementation.inc"

i64 wait_for(u64 child, u64 output, u64 flags = 0) {
    interrupt_frame frame{};
    frame.rax = sys_process_wait;
    frame.rdi = child;
    frame.rsi = output;
    frame.rdx = flags;
    assert(wait_syscall(&frame) == &frame);
    return static_cast<i64>(frame.rax);
}

void reset() {
    for (auto& task : tasks) { task = {}; }
    for (auto& thread : threads) { thread = {}; }
    for (auto& endpoint : endpoints) { endpoint = {}; }
    files_pid = 0;
#if XOS_IPC_DEADLINES
    for (auto& connection : ipc_connections) connection = {};
    for (auto& call : ipc_v1_calls) call = {};
    clock::host_now = 100;
#endif
    for (auto& item : completions) { item = {}; }
    for (auto& pending : reap_pending) { pending = false; }
    schedules = 0;
    host_write_allowed = true;
    tasks[0].pid = 1;
    tasks[0].state = task_state::running;
    tasks[0].can_create = true;
    tasks[1].pid = 2;
    tasks[1].parent = 1;
#if XOS_RUNTIME_VM
    tasks[1].cancel_parent = 1;
#endif
    tasks[1].state = task_state::ready;
    tasks[1].completion_slot = 1;
    completions[0].used = true;
#if XOS_PROCESS_WAIT_ANY
    completions[0].published = true;
#endif
    completions[0].parent = 1;
    completions[0].status.pid = 2;
    for (u32 i = 0; i < 4; ++i) {
        threads[i].process = &tasks[0];
        threads[i].tid = i + 1;
        threads[i].state = thread_state::running;
    }
    current = &tasks[0];
    current_thread = &threads[0];
}

void second_child() {
    tasks[2].pid = 3;
    tasks[2].parent = 1;
    tasks[2].state = task_state::ready;
    tasks[2].completion_slot = 2;
    completions[1].used = true;
#if XOS_PROCESS_WAIT_ANY
    completions[1].published = true;
#endif
    completions[1].parent = 1;
    completions[1].status.pid = 3;
}
#if XOS_IPC_DEADLINES
i64 wait_ipc(interrupt_frame& frame, ipc_wait_mode mode, u64 deadline) {
    current_thread->kernel_rsp = reinterpret_cast<u64>(&frame);
    frame = {}; frame.rax = sys_ipc_wait; frame.rdi = 42;
    frame.rsi = static_cast<u64>(mode); frame.rdx = deadline;
    assert(ipc_wait_syscall(&frame) == &frame);
    return static_cast<i64>(frame.rax);
}
void generic_endpoint(bool sending = false) {
    reset();
    endpoints[0].used = endpoints[0].generic = true;
    endpoints[0].handle = endpoints[0].channel_id = 42;
    endpoints[0].sender_pid = sending ? 1 : 2;
    endpoints[0].receiver_pid = sending ? 2 : 1;
    endpoints[0].pending = sending;
}
void deadline_tests() {
    interrupt_frame frame{};
    for (bool sending : {false, true}) {
        const auto mode = sending ? ipc_wait_mode::send_until : ipc_wait_mode::receive_until;
        for (bool close_first : {false, true}) {
            generic_endpoint(sending);
            assert(wait_ipc(frame, mode, 200) == 0 && current_thread->state == thread_state::blocked);
            clock::host_now = 199; expire_waiters();
            assert(current_thread->state == thread_state::blocked);
            clock::host_now = 200;
            if (close_first) revoke_ipc_channel(42, pipe_error_broken);
            expire_waiters();
            if (!close_first) {
                assert(endpoints[0].used && endpoints[0].pending == sending);
                revoke_ipc_channel(42, pipe_error_broken);
            }
            const i64 expected = close_first ? pipe_error_broken : thread_error_timeout;
            assert(current_thread->state == thread_state::ready && static_cast<i64>(frame.rax) == expected);
            expire_waiters(); revoke_ipc_channel(42, pipe_error_broken);
            assert(static_cast<i64>(frame.rax) == expected && current_thread->wait_kind == thread_wait_kind::none);
        }
    }
    std::puts("PASS IPC deadlines: exact deadline close/timeout both orders for send and receive complete once");

    for (bool sending : {false, true}) {
        const auto mode = sending ? ipc_wait_mode::send_until : ipc_wait_mode::receive_until;
        for (u64 deadline : {u64{0}, u64{99}, u64{100}}) {
            generic_endpoint(sending);
            assert(wait_ipc(frame, mode, deadline) == thread_error_timeout && schedules == 0);
            assert(endpoints[0].pending == sending);
            endpoints[0].pending = !sending;
            assert(wait_ipc(frame, mode, deadline) == 0 && schedules == 0);
            assert(endpoints[0].pending == !sending);
        }
    }
    std::puts("PASS IPC deadlines: zero and expired fast paths preserve queues and prefer readiness");

    for (u64 deadline : {~u64{0} - 1, ~u64{0}}) {
        generic_endpoint(true);
        assert(wait_ipc(frame, ipc_wait_mode::send_until, deadline) == 0);
        clock::host_now = ~u64{0} - 2; expire_waiters();
        assert(current_thread->state == thread_state::blocked);
        clock::host_now = deadline; expire_waiters();
        if (deadline == ~u64{0}) {
            assert(current_thread->state == thread_state::blocked);
            revoke_ipc_channel(42, pipe_error_broken);
            assert(static_cast<i64>(frame.rax) == pipe_error_broken);
        } else assert(static_cast<i64>(frame.rax) == thread_error_timeout);
    }
    std::puts("PASS IPC deadlines: full-width absolute deadlines do not wrap and infinity stays blocked");

    generic_endpoint();
    assert(wait_ipc(frame, ipc_wait_mode::receive, 0) == 0);
    clock::host_now = 1000; expire_waiters();
    assert(current_thread->state == thread_state::blocked);
    revoke_ipc_channel(42, pipe_error_broken);
    assert(static_cast<i64>(frame.rax) == pipe_error_broken);
    generic_endpoint(); endpoints[0].generic = false; endpoints[0].session_response = true;
    endpoints[0].owner_pid = current->pid; endpoints[0].pending = true;
    files_pid = 2; tasks[1].block_access = true;
    current->recv_handle = current->session_response_handle = 42;
    assert(wait_ipc(frame, ipc_wait_mode::file_reply_until, 100) == thread_error_timeout);
    assert(endpoints[0].pending && schedules == 0);
    assert(wait_ipc(frame, ipc_wait_mode::receive_until, 200) == process_error_denied);
    std::puts("PASS IPC deadlines: legacy indefinite and Files-only deadline precedence stay unchanged");
}
#endif
}
}

int main() {
    using namespace xos;
    using namespace xos::arch;
#if XOS_IPC_DEADLINES
    deadline_tests();
#endif
    void* memory = mmap(reinterpret_cast<void*>(process_user_begin), 3 * page_size,
                        PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE,
                        -1, 0);
    assert(memory == reinterpret_cast<void*>(process_user_begin));
    const u64 first_output = process_user_begin + page_size - 16;
    const u64 second_output = process_user_begin + 2 * page_size;
    auto* first_status = reinterpret_cast<process_status*>(first_output);
    auto* second_status = reinterpret_cast<process_status*>(second_output);

    reset();
    files_pid = tasks[1].pid;
    endpoints[0].used = true;
    endpoints[0].session_response = true;
    endpoints[0].sender_pid = files_pid;
    endpoints[0].receiver_pid = tasks[0].pid;
    endpoints[0].handle = 42;
    interrupt_frame file_wait_frames[3]{};
    for (u32 index = 0; index < 3; ++index) {
        threads[index].kernel_rsp = reinterpret_cast<u64>(&file_wait_frames[index]);
        threads[index].state = thread_state::blocked;
        threads[index].wait_kind = index == 1 ? thread_wait_kind::ipc_send : thread_wait_kind::ipc_receive;
        threads[index].wait_target = index == 2 ? 43 : 42;
    }
    finish_task(&tasks[1], process_outcome::exited, 0);
    assert(threads[0].state == thread_state::ready && threads[0].wait_kind == thread_wait_kind::none);
    assert(static_cast<i64>(file_wait_frames[0].rax) == pipe_error_broken);
    assert(threads[1].state == thread_state::blocked && threads[2].state == thread_state::blocked);
    assert(completions[0].ready && reap_pending[1]);
    std::puts("PASS process exit: Files death wakes only its blocked reply receivers with broken");

    for (u64 competing_flags = 0; competing_flags <= 1; ++competing_flags) {
        reset();
        *first_status = {};
        *second_status = {};
        assert(wait_for(2, first_output) == 0);
        assert(schedules == 1 && threads[0].state == thread_state::blocked);
        assert(threads[0].user_pin.overlaps(process_user_begin, process_user_begin + page_size));
        assert(threads[0].user_pin.overlaps(process_user_begin + page_size, second_output));

        current_thread = &threads[1];
        assert(wait_for(2, second_output, 1) == process_error_would_block);
        assert(wait_for(2, second_output) == thread_error_busy);
        finish_task(&tasks[1], process_outcome::exited, 37);
        assert(threads[0].state == thread_state::ready && completions[0].ready);
        assert(reap_pending[1]);

        // Keep the original waiter off-CPU until the competing syscall returns.
        assert(wait_for(2, second_output, competing_flags) == thread_error_busy);
        assert(completions[0].used && threads[0].user_pin.active());
        assert(first_status->version == 0 && second_status->version == 0);

        interrupt_frame resumed{};
        current_thread = &threads[0];
        deliver_wait(current_thread, &resumed);
        assert(resumed.rax == 0 && first_status->pid == 2 && first_status->code == 37);
        assert(first_status->outcome == process_outcome::exited);
        assert(!completions[0].used && !current_thread->user_pin.active());
        assert(current_thread->wait_kind == thread_wait_kind::none && current_thread->wait_target == 0);
        assert(wait_for(2, second_output) == process_error_denied);
    }

    reset();
    finish_task(&tasks[1], process_outcome::killed, -9);
    assert(wait_for(2, second_output, 1) == 0);
    assert(second_status->pid == 2 && second_status->code == -9 && !completions[0].used);
    assert(schedules == 0 && !current_thread->user_pin.active());
#if XOS_RUNTIME_VM
    const process_outcome normal_outcomes[] = {process_outcome::exited, process_outcome::faulted};
    for (auto outcome : normal_outcomes) {
        reset();
        finish_task(&tasks[0], outcome, 0);
        assert(tasks[1].state == task_state::ready && tasks[1].parent == 0);
        assert(tasks[1].completion_slot == 0 && !completions[0].used);
        finish_task(&tasks[1], process_outcome::exited, 0);
        assert(reap_pending[1] && !completions[0].used);
    }
    reset();
    tasks[1].state = task_state::building;
    finish_task(&tasks[0], process_outcome::exited, 0);
    assert(tasks[1].state == task_state::dead && reap_pending[1]);

    reset();
    tasks[2].pid = 3;
    tasks[2].parent = tasks[2].cancel_parent = 2;
    tasks[2].state = task_state::ready;
    finish_task(&tasks[1], process_outcome::exited, 0);
    assert(tasks[2].state == task_state::ready && tasks[2].parent == 0 && tasks[2].cancel_parent == 1);
    finish_task(&tasks[0], process_outcome::killed, -9);
    assert(tasks[2].state == task_state::dead && reap_pending[2]);

    reset();
    tasks[1].cpu = {70, 30};
    tasks[1].child_cpu = {5, 7};
    finish_task(&tasks[1], process_outcome::exited, 0);
    assert(tasks[0].child_cpu.user == 0 && tasks[0].child_cpu.system == 0);
    assert(wait_for(2, second_output, 1) == 0);
    assert(tasks[0].child_cpu.user == 75 && tasks[0].child_cpu.system == 37);
    assert(wait_for(2, second_output, 1) == process_error_denied);
    assert(tasks[0].child_cpu.user == 75 && tasks[0].child_cpu.system == 37);
    std::puts("PASS normal/fault parent exit, orphan cleanup, builder cancellation, explicit kill ancestry, child CPU consumption");
#endif
    reset();
    *second_status = {99, process_outcome::exited, 123, 57, 0, 0, 0};
    assert(wait_for(0, second_output, process_wait_any | process_wait_nonblocking) == process_error_would_block);
    assert(wait_for(2, second_output, process_wait_any) == process_error_invalid);
    assert(wait_for(0, second_output, 4) == process_error_invalid);
    assert(wait_for(0, second_output) == process_error_denied);
    assert(wait_for(0, process_user_begin + 3 * page_size - 8,
                    process_wait_any | process_wait_nonblocking) == process_error_invalid);
    assert(second_status->version == 99 && second_status->pid == 123 && second_status->code == 57);
    tasks[1].state = task_state::building;
#if XOS_PROCESS_WAIT_ANY
    completions[0].published = false;
#endif
    assert(wait_for(0, second_output, process_wait_any) == process_error_denied);
    finish_task(&tasks[1], process_outcome::killed, -9);
    assert(wait_for(0, second_output, process_wait_any) == process_error_denied);
    assert(completions[0].used && wait_for(2, second_output, 1) == 0);
    std::puts("PASS wait-any: flags, nohang, output preservation, building and killed-builder invisibility");

    reset();
    *first_status = {}; *second_status = {99, process_outcome::exited, 123, 57, 0, 0, 0};
    assert(wait_for(0, first_output, process_wait_any) == 0);
    finish_task(&tasks[1], process_outcome::exited, 37);
    assert(threads[0].state == thread_state::ready && threads[0].wait_target == 2);
    current_thread = &threads[1];
    assert(wait_for(0, second_output, process_wait_any | process_wait_nonblocking) == process_error_would_block);
    assert(wait_for(0, second_output, process_wait_any) == 0);
    assert(threads[1].state == thread_state::blocked && threads[1].wait_target == 0);
    interrupt_frame resumed{};
    current_thread = &threads[0];
    deliver_wait(current_thread, &resumed);
    assert(resumed.rax == 0 && first_status->pid == 2 && first_status->code == 37);
    assert(threads[1].state == thread_state::ready && threads[1].wait_target == ~u64{0});
    current_thread = &threads[1];
    deliver_wait(current_thread, &resumed);
    assert(static_cast<i64>(resumed.rax) == process_error_denied);
    assert(second_status->version == 99 && second_status->pid == 123 && second_status->code == 57);
    assert(!threads[0].user_pin.active() && !threads[1].user_pin.active());
    std::puts("PASS wait-any: deferred claim survives polling and wakes last-child competitors");

    for (bool precise_first : {false, true}) {
        reset(); second_child();
        *first_status = {}; *second_status = {};
        assert(wait_for(precise_first ? 2 : 0, first_output,
                        precise_first ? 0 : process_wait_any) == 0);
        current_thread = &threads[1];
        assert(wait_for(0, second_output, process_wait_any) == 0);
        finish_task(&tasks[1], process_outcome::faulted, -1, 14, 1234, 5678);
        finish_task(&tasks[2], process_outcome::killed, -9);
        assert(threads[0].wait_target == 2 && threads[1].wait_target == 3);
        current_thread = &threads[2];
        assert(wait_for(0, second_output, process_wait_any | process_wait_nonblocking) == process_error_would_block);
        assert(wait_for(2, second_output, 1) == thread_error_busy);
        current_thread = &threads[1];
        deliver_wait(current_thread, &resumed);
        assert(resumed.rax == 0 && second_status->pid == 3 && second_status->outcome == process_outcome::killed);
        current_thread = &threads[0];
        deliver_wait(current_thread, &resumed);
        assert(resumed.rax == 0 && first_status->pid == 2 && first_status->outcome == process_outcome::faulted);
        assert(first_status->vector == 14 && first_status->address == 1234 && first_status->instruction == 5678);
        assert(wait_for(0, second_output, process_wait_any) == process_error_denied);
    }
    std::puts("PASS wait-any: exact priority and multiple-any fault/kill unique consumption");

    reset();
    *first_status = {99, process_outcome::exited, 123, 57, 0, 0, 0}; *second_status = {};
    assert(wait_for(0, first_output, process_wait_any) == 0);
    current_thread = &threads[1];
    assert(wait_for(0, second_output, process_wait_any) == 0);
    tasks[1].cpu = {70, 30};
    finish_task(&tasks[1], process_outcome::exited, 23);
    current_thread = &threads[0];
    host_write_allowed = false;
    deliver_wait(current_thread, &resumed);
    assert(static_cast<i64>(resumed.rax) == process_error_invalid);
    assert(first_status->version == 99 && first_status->pid == 123 && first_status->code == 57);
    assert(completions[0].used && !threads[0].user_pin.active());
    assert(threads[1].state == thread_state::ready && threads[1].wait_target == 2);
    assert(tasks[0].child_cpu.user == 0 && tasks[0].child_cpu.system == 0);
    host_write_allowed = true;
    current_thread = &threads[1];
    deliver_wait(current_thread, &resumed);
    assert(resumed.rax == 0 && second_status->pid == 2 && second_status->code == 23);
    assert(tasks[0].child_cpu.user == 70 && tasks[0].child_cpu.system == 30);
    assert(!completions[0].used && !threads[1].user_pin.active());
    std::puts("PASS wait-any: failed deferred copyout returns claim, preserves output and accounts CPU once");

    reset();
    assert(wait_for(0, first_output, process_wait_any) == 0);
    finish_task(&tasks[0], process_outcome::exited, 0);
    assert(threads[0].state == thread_state::dead && !threads[0].user_pin.active());
    assert(!completions[0].used && tasks[1].parent == 0 && tasks[1].state == task_state::ready);
    std::puts("PASS wait-any: parent exit releases pin and retains ordinary orphan lifecycle");

    reset();
    finish_task(&tasks[1], process_outcome::exited, 41);
    tasks[3].pid = 99; tasks[3].state = task_state::running;
    current = &tasks[3]; current_thread = &threads[3]; threads[3].process = current;
    assert(wait_for(0, second_output, process_wait_any) == process_error_denied);
    assert(completions[0].used);
    current = &tasks[0]; current_thread = &threads[0];
    assert(wait_for(0, second_output, process_wait_any | process_wait_nonblocking) == 0);
    assert(second_status->pid == 2 && second_status->code == 41 && !completions[0].used);
    std::puts("PASS wait-any: authenticated parent selection and ready nonblocking consumption");
    assert(munmap(memory, 3 * page_size) == 0);
    std::puts("PASS process wait: pending duplicate, ready owner, cross-page pin, delivery, single consumption");
}
