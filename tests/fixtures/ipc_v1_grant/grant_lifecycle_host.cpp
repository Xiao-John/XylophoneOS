// SPDX-License-Identifier: Apache-2.0
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <xos/audio_abi.hpp>
#include <xos/device_abi.hpp>
#include <xos/ipc_v1_abi.hpp>
#include <xos/memory.hpp>
#include "core/anonymous_reservations.hpp"
#include "core/cpu_accounting.hpp"
#include "core/device_grants.hpp"
#include "core/thread_lifecycle.hpp"
#include "core/user_copyout.hpp"
#include "core/vm_continuation.hpp"
#include "core/vm_pin.hpp"
#include "arch/x86_64/frame.hpp"

namespace xos::arch {
namespace {
#include "grant_records.inc"
process_record tasks[8];
thread_record threads[thread_max_total];
process_record* current;
thread_record* current_thread;
endpoint_record endpoints[max_endpoints];
u64 next_endpoint_handle = 1;
fork_copy_transaction fork_copies[8];
ipc_v1_grant_handle_record ipc_v1_grant_handles[ipc_v1_max_grants_system * ipc_v1_max_handles_per_process];
ipc_v1_grant_mapping_record ipc_v1_grant_mappings[ipc_v1_max_grant_mappings_system];
anonymous_vm::reservations vm1_probe_regions[8], ipc_v1_close_regions;
device_grants::store device_store;
u32 files_checks, scenarios;

bool files_service_live() { ++files_checks; return false; }
process_record* prepare_task(const char*) { std::abort(); }
void destroy_task(process_record*) { std::abort(); }
void fpu_save(u8*) { std::abort(); }
vm_step fork_copy_step(void*, vm_phase, u32, i64&) { std::abort(); }
bool begin_vm_continuation(process_record&, thread_record&, void*, vm_step_function) { std::abort(); }

#include "grant_implementation.inc"

constexpr u64 base = anonymous_vm::arena_begin + 0x100000;
void reset() {
    for (auto& task : tasks) task = {};
    for (auto& thread : threads) thread = {};
    for (auto& handle : ipc_v1_grant_handles) handle = {};
    for (auto& mapping : ipc_v1_grant_mappings) mapping = {};
    for (auto& regions : vm1_probe_regions) regions.clear();
    ipc_v1_close_regions.clear(); files_checks = 0;
    tasks[0].pid = 11; tasks[0].state = task_state::running; tasks[0].can_create = true;
    tasks[1].pid = 22; tasks[1].state = task_state::ready;
    current = &tasks[0]; current_thread = &main_thread(current);
    current_thread->process = current; current_thread->main = true;
    current_thread->state = thread_state::running;
}
void seed(anonymous_vm::reservations& regions, u32 fragments) {
    assert(regions.reserve(base, 5 * page_size, page_size, true) == static_cast<i64>(base));
    for (u32 i = 1; i < fragments; ++i) {
        const u64 at = base + (8 + 2 * u64{i}) * page_size;
        assert(regions.reserve(at, page_size, page_size, true) == static_cast<i64>(at));
    }
    assert(regions.count() == fragments);
}
void mapping(u32 index, u64 owner, u64 address, u32 grant = 0) {
    ipc_v1_grant_mappings[index] = {true, grant, 1, 3, index + 1, owner, address};
}
void unchanged(const anonymous_vm::reservations& expected, const anonymous_vm::reservations& actual) {
    assert(expected.count() == actual.count() && expected.bytes() == actual.bytes());
    for (u32 i = 0; i < expected.count(); ++i) {
        assert(expected.at(i).begin == actual.at(i).begin && expected.at(i).end == actual.at(i).end);
    }
}
void close_preflight() {
    reset(); seed(vm1_probe_regions[0], 255);
    mapping(0, 11, base + page_size); mapping(1, 11, base + 3 * page_size);
    const auto full = vm1_probe_regions[0];
    assert(full.can_unmap(base + page_size, page_size));
    assert(full.can_unmap(base + 3 * page_size, page_size));
    assert(ipc_v1_grant_close_status(0) == static_cast<i64>(ipc_v1_error::resources));
    unchanged(full, vm1_probe_regions[0]);
    assert(ipc_v1_grant_mappings[0].used && ipc_v1_grant_mappings[1].used);
    ++scenarios;

    reset(); seed(vm1_probe_regions[0], 254);
    mapping(0, 11, base + page_size); mapping(1, 11, base + 3 * page_size);
    const auto enough = vm1_probe_regions[0];
    assert(ipc_v1_grant_close_status(0) == 0); unchanged(enough, vm1_probe_regions[0]);
    assert(vm1_probe_regions[0].unmap(base + page_size, page_size) == 0);
    assert(vm1_probe_regions[0].unmap(base + 3 * page_size, page_size) == 0);
    assert(vm1_probe_regions[0].count() == 256);
    ++scenarios;

    reset(); seed(vm1_probe_regions[0], 256);
    mapping(0, 11, vm1_probe_regions[0].at(1).begin); mapping(1, 11, base + page_size);
    const auto ordered = vm1_probe_regions[0];
    assert(ipc_v1_grant_close_status(0) == 0); unchanged(ordered, vm1_probe_regions[0]);
    const auto first = ipc_v1_grant_mappings[0];
    ipc_v1_grant_mappings[0] = ipc_v1_grant_mappings[1]; ipc_v1_grant_mappings[1] = first;
    assert(ipc_v1_grant_close_status(0) == static_cast<i64>(ipc_v1_error::resources));
    unchanged(ordered, vm1_probe_regions[0]);
    ++scenarios;

    reset(); seed(vm1_probe_regions[0], 254); seed(vm1_probe_regions[1], 255);
    mapping(0, 11, base + page_size); mapping(1, 11, base + 3 * page_size);
    mapping(2, 22, base + page_size); mapping(3, 22, base + 3 * page_size);
    const auto owner0 = vm1_probe_regions[0], owner1 = vm1_probe_regions[1];
    assert(ipc_v1_grant_close_status(0) == static_cast<i64>(ipc_v1_error::resources));
    unchanged(owner0, vm1_probe_regions[0]); unchanged(owner1, vm1_probe_regions[1]);
    ++scenarios;

    reset(); seed(vm1_probe_regions[0], 1); mapping(0, 11, base + page_size);
    current_thread->state = thread_state::blocked;
    current_thread->wait_kind = thread_wait_kind::device_irq;
    assert(current_thread->ipc_v1_pins[0].set(base + page_size + 24, sizeof(device_output)));
    int context = 0;
    assert(current->continuation.begin(1, 1, &context, fork_copy_step));
    assert(ipc_v1_grant_close_status(0) == static_cast<i64>(ipc_v1_error::busy));
    current_thread->ipc_v1_pins[0].clear();
    assert(ipc_v1_grant_close_status(0) == static_cast<i64>(ipc_v1_error::state));
    current->continuation.clear(); assert(ipc_v1_grant_close_status(0) == 0);
    ++scenarios;
}
void fork_admission() {
    interrupt_frame frame{};
    reset(); mapping(0, 11, base);
    assert(prepare_fork(&frame) == process_error_busy && files_checks == 0);
    ++scenarios;

    reset(); mapping(0, 22, base);
    assert(prepare_fork(&frame) == process_error_resources && files_checks == 1);
    ++scenarios;

    reset(); ipc_v1_grant_handles[0] = {true, 0, 1, 9, 11};
    assert(prepare_fork(&frame) == process_error_resources && files_checks == 1);
    assert(ipc_v1_grant_handles[0].used);
    ++scenarios;
}
}
}

int main() {
    xos::arch::close_preflight(); xos::arch::fork_admission();
    std::printf("IPC_GRANT_LIFECYCLE_SCENARIOS_PASSED=%u cow=%u\n", xos::arch::scenarios, XOS_COW_FORK);
}
