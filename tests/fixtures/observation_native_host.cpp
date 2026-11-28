// SPDX-License-Identifier: Apache-2.0
#include <cassert>
#include <cstdio>
#include <cstring>
#include <xos/thread_abi.hpp>
#include <xos/observation_abi.hpp>
#include <xos/device_abi.hpp>
#include <xos/ipc_v1_abi.hpp>
#include "core/thread_lifecycle.hpp"
#include "core/vm_pin.hpp"
#include "core/vm_continuation.hpp"
#include "core/user_copyout.hpp"
#include "core/cpu_accounting.hpp"
#include "arch/x86_64/frame.hpp"

namespace xos::clock {
u64 now = 100, step = 0;
u64 monotonic_ns() { const auto value = now; now += step; return value; }
}
namespace xos::arch {
namespace {
#include "observation_records.inc"
process_record tasks[8];
thread_record threads[thread_max_total];
endpoint_record endpoints[max_endpoints];
ipc_name_record ipc_names[8];
process_record* current = &tasks[0];
u64 input_address, output_address;
bool writable = true, deadline_during_copy = false;

bool user_range_ok(u64 address, u64 size, bool write) {
    if (write && deadline_during_copy) clock::now = 500;
    return write ? writable && address == output_address && size == sizeof(observe_native::snapshot)
                 : address == input_address && size == sizeof(observe_native::request);
}
void copy_from_user(void* destination, u64 source, u64 size) {
    std::memcpy(destination, reinterpret_cast<const void*>(source), size);
}
void copy_to_user(u64 destination, const void* source, u64 size) {
    std::memcpy(reinterpret_cast<void*>(destination), source, size);
}

#include "observation_implementation.inc"

using namespace observe_native;
request query_for(query kind, u64 target = 0) {
    return {version, sizeof(request), kind, 0, target, 0, 0, 500};
}
void reset() {
    for (auto& task : tasks) task = {};
    for (auto& thread : threads) thread = {};
    for (auto& endpoint : endpoints) endpoint = {};
    for (auto& name : ipc_names) name = {};
    clock::now = 100; clock::step = 0;
    writable = true; deadline_during_copy = false;
    tasks[0].pid = 10; tasks[0].parent = 1; tasks[0].state = task_state::running;
    tasks[0].image_generation = 2; tasks[0].user_pages = 40;
    tasks[0].pipe_reference_count = 3; tasks[0].ticks = 17;
    tasks[1].pid = 11; tasks[1].parent = 10; tasks[1].state = task_state::ready;
    tasks[1].image_generation = 1; tasks[1].user_pages = 9;
    tasks[2].pid = 12; tasks[2].parent = 11; tasks[2].state = task_state::running;
    tasks[2].image_generation = 7; tasks[2].user_pages = 999;
    tasks[3].pid = 13; tasks[3].parent = 1; tasks[3].state = task_state::waiting;
    tasks[3].image_generation = 3; tasks[3].user_pages = 888;
    threads[0].process = current; threads[0].state = thread_state::running;
    threads[1].process = current; threads[1].state = thread_state::blocked;
    threads[2].process = &tasks[3]; threads[2].state = thread_state::blocked;
    endpoints[0].used = true; endpoints[0].generic = true;
    endpoints[0].handle = endpoints[0].channel_id = 40;
    endpoints[0].sender_pid = endpoints[0].owner_pid = 10;
    endpoints[0].receiver_pid = 13;
    endpoints[1] = endpoints[0]; endpoints[1].handle = 41;
    endpoints[1].sender_pid = 13; endpoints[1].receiver_pid = 10;
    ipc_names[0].used = true; ipc_names[0].owner_pid = 10;
    ipc_names[1].used = true; ipc_names[1].owner_pid = 13;
}
bool zero(const snapshot& value) {
    const snapshot empty{};
    return !std::memcmp(&value, &empty, sizeof(value));
}
void check_scope() {
    reset(); snapshot out{};
    auto req = query_for(query::process);
    assert(observe_snapshot(req, out) == result::ok);
    assert(out.pid == 10 && out.parent_pid == 1 && out.image_generation == 2 && out.ticks == 17);
    assert(out.threads == 2 && out.blocked_threads == 1 && out.process_state == state::running);
    assert(out.version == version && out.size == sizeof(out) && out.pages == 0);
    threads[0].state = thread_state::blocked;
    assert(observe_snapshot(req, out) == result::ok && out.process_state == state::waiting &&
           out.threads == 2 && out.blocked_threads == 2);
    threads[0].state = thread_state::ready;
    assert(observe_snapshot(req, out) == result::ok && out.process_state == state::ready);
    req.target = 11;
    assert(observe_snapshot(req, out) == result::ok && out.pid == 11);
    req.target = 12;
    assert(observe_snapshot(req, out) == result::denied && zero(out));
    req.target = 13;
    assert(observe_snapshot(req, out) == result::denied && zero(out));
    current->supervisor = true;
    assert(observe_snapshot(req, out) == result::denied && zero(out));
    req.target = 999;
    assert(observe_snapshot(req, out) == result::denied && zero(out));
    std::puts("PASS process scope: self/direct child only; supervisor cannot enumerate unrelated tasks");
}
void check_identity() {
    reset(); snapshot out{};
    auto req = query_for(query::process, 11);
    req.expected_pid = 11; req.expected_generation = 1;
    assert(observe_snapshot(req, out) == result::ok);
    tasks[1].image_generation = 2;
    assert(observe_snapshot(req, out) == result::stale && zero(out));
    req.expected_pid = 99;
    assert(observe_snapshot(req, out) == result::stale && zero(out));
    req.target = 13;
    assert(observe_snapshot(req, out) == result::denied && zero(out));
    std::puts("PASS generation preconditions follow authorization; stale image rejected without state");
}
void check_resources() {
    reset(); snapshot out{};
    auto req = query_for(query::resources);
    assert(observe_snapshot(req, out) == result::ok);
    assert(out.pages == 40 && out.page_limit == process_max_pages);
    assert(out.threads == 2 && out.blocked_threads == 1);
    assert(out.owned_channels == 1 && out.channel_limit == ipc_max_owned_channels);
    assert(out.owned_names == 1 && out.name_limit == ipc_max_owned_names);
    assert(out.pipe_references == 3 && out.pipe_reference_limit == process_max_pipe_refs);
    req.target = 11;
    assert(observe_snapshot(req, out) == result::ok && out.pages == 9 && out.threads == 0);
    std::puts("PASS scoped resource accounting; pair counted once, unrelated owner excluded");
}
void check_service() {
    reset(); snapshot out{};
    auto req = query_for(query::service, 40);
    req.expected_pid = 13; req.expected_generation = 3;
    assert(observe_snapshot(req, out) == result::ok);
    assert(out.pid == 13 && out.image_generation == 3 && out.object_token == 40);
    assert(out.flags == flag_service_published && out.parent_pid == 0 && out.pages == 0 && out.ticks == 0);
    req.target = 41;
    assert(observe_snapshot(req, out) == result::ok);
    endpoints[1].receiver_pid = 11;
    assert(observe_snapshot(req, out) == result::denied && zero(out));
    endpoints[1] = {};
    assert(observe_snapshot(req, out) == result::denied && zero(out));
    req.target = 40; tasks[3].closing = true;
    assert(observe_snapshot(req, out) == result::unavailable && zero(out));
    tasks[3].closing = false; tasks[3].pid = 14;
    endpoints[0].receiver_pid = 14;
    assert(observe_snapshot(req, out) == result::stale && zero(out));
    std::puts("PASS held endpoint peer only; revoked/foreign handles disclose no peer; restart mismatches rejected");
}
void check_deadline_and_format() {
    reset(); snapshot out{};
    auto req = query_for(query::process);
    req.deadline_ns = 0;
    assert(observe_snapshot(req, out) == result::invalid && zero(out));
    req.deadline_ns = ~u64{0};
    assert(observe_snapshot(req, out) == result::invalid && zero(out));
    req.deadline_ns = 100;
    assert(observe_snapshot(req, out) == result::deadline && zero(out));
    req.deadline_ns = 500; clock::step = 400;
    assert(observe_snapshot(req, out) == result::deadline && zero(out));
    clock::step = 0; clock::now = 100;
    req.version = 2;
    assert(observe_snapshot(req, out) == result::invalid && zero(out));
    req.version = version; req.size--;
    assert(observe_snapshot(req, out) == result::invalid && zero(out));
    req.size = sizeof(req); req.reserved = 1;
    assert(observe_snapshot(req, out) == result::invalid && zero(out));
    req.reserved = 0; req.kind = static_cast<query>(4);
    assert(observe_snapshot(req, out) == result::invalid && zero(out));
    std::puts("PASS version/size/reserved/kind and finite absolute deadline enforced before and after scan");
}
void check_dispatch() {
    reset(); auto req = query_for(query::resources); snapshot out{};
    interrupt_frame frame{}; frame.rax = sys_observe;
    input_address = frame.rdi = reinterpret_cast<u64>(&req);
    output_address = frame.rsi = reinterpret_cast<u64>(&out);
    assert(observe_call(frame) == 0 && out.pid == current->pid);
    out = {}; writable = false;
    assert(observe_call(frame) == static_cast<i64>(result::invalid) && zero(out));
    writable = true; frame.rdi++;
    assert(observe_call(frame) == static_cast<i64>(result::invalid) && zero(out));
    frame.rdi--; frame.rdx = 1;
    assert(observe_call(frame) == static_cast<i64>(result::invalid) && zero(out));
    frame.rdx = 0; deadline_during_copy = true;
    assert(observe_call(frame) == static_cast<i64>(result::deadline) && zero(out));
    std::puts("PASS real syscall copy boundary: alignment, reserved argument, unwritable output, late copy deadline");
}
}
}

int main() {
    using namespace xos::arch;
    check_scope(); check_identity(); check_resources(); check_service();
    check_deadline_and_format(); check_dispatch();
}
