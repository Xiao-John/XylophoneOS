// SPDX-License-Identifier: Apache-2.0
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <sys/mman.h>
#include <unistd.h>
#include <xos/memory.hpp>
#include <xos/audio_abi.hpp>
#include <xos/device_abi.hpp>
#include <xos/display_abi.hpp>
#include <xos/ipc_v1_abi.hpp>
#include <xos/syscall.hpp>
#include <xos/format.hpp>
#include <xos/platform.hpp>
#include "core/thread_lifecycle.hpp"
#include "core/stream_lease.hpp"
#include "core/vm_pin.hpp"
#include "core/vm_continuation.hpp"
#include "core/user_copyout.hpp"
#include "core/cpu_accounting.hpp"
#include "core/device_grants.hpp"
#include "arch/x86_64/cow1_probe.hpp"
#include "arch/x86_64/frame.hpp"

xos::u64 host_active_cr3;
namespace {
using namespace xos;
constexpr u64 physical_base = 0x10000000, physical_bytes = 32 * 1024 * 1024;
constexpr u64 user_address = 0x40000000;
int physical_fd;
u32 console_reads, wakeups;
}

void host_invalidate(xos::u64 address) {
    using namespace xos;
    if (address < user_address || address >= user_address + 2 * page_size) { return; }
    u64 physical;
    page_permissions permissions{};
    if (query_page_in(host_active_cr3, address, &physical, &permissions) != memory_result::none) { return; }
    const int access = PROT_READ | (permissions.writable ? PROT_WRITE : 0);
    assert(mmap(reinterpret_cast<void*>(address), page_size, access, MAP_SHARED | MAP_FIXED,
                physical_fd, static_cast<off_t>(physical - physical_base)) == reinterpret_cast<void*>(address));
}

namespace xos::platform {
bool debug_write(const char*) { return true; }
bool debug_serial_attached() { return true; }
int debug_read() { ++console_reads; return 'x'; }
}
namespace xos::clock {
u64 monotonic_ns() { std::abort(); }
}
namespace xos::arch {
[[noreturn]] void halt() { std::abort(); }
namespace {
#include "kernel_copyout_records.inc"
process_record owner;
thread_record caller;
process_record* current = &owner;
thread_record* current_thread = &caller;
endpoint_record endpoints[1];
pipe_object pipes[process_max_pipes];
stream_lease input_lease;
constexpr u32 display_request_handle = 99;
bool display_delivered, display_presented;
bool display_endpoint(u64) { return false; }
const process_record* task_by_pid(u64) { return nullptr; }
void wake_channel_waiters(u32, bool, bool, i64) { ++wakeups; }
void wake_ipc_waiters(u32, i64, thread_wait_kind) { ++wakeups; }
void wake_pipe_waiters(u32, bool, bool) { ++wakeups; }
i64 (*operation)();
device_grants::store device_store;
device_grants::backend device_backend{};
bool device_grant_allowed(void*, u64 issuer, u64 target) { return issuer == 2 && target == 1; }
i64 device_description(void*, u64, u64, device_grants::description& out) {
    out = {}; out.bars[0] = {0xe0000000, 16384}; return 0;
}
void* schedule(interrupt_frame*) { std::abort(); }
void* device_authorize_syscall(interrupt_frame*);
void* dispatch_syscall(interrupt_frame* frame) {
    if (frame->rax == sys_device) return device_authorize_syscall(frame);
    frame->rax = static_cast<u64>(operation()); return frame;
}
#include "kernel_copyout_implementation.inc"

i64 invoke(u64 number, i64 (*body)(), u64 first = 0) {
    operation = body;
    interrupt_frame frame{};
    frame.rax = number;
    frame.rdi = first;
    assert(syscall_entry(&frame) == &frame);
    return static_cast<i64>(frame.rax);
}
}
}

int main() {
    using namespace xos;
    using namespace xos::arch;
    physical_fd = memfd_create("xos_copyout", MFD_CLOEXEC);
    assert(physical_fd >= 0 && ftruncate(physical_fd, physical_bytes) == 0);
    assert(mmap(reinterpret_cast<void*>(physical_base), physical_bytes, PROT_READ | PROT_WRITE,
                MAP_SHARED | MAP_FIXED_NOREPLACE, physical_fd, 0) == reinterpret_cast<void*>(physical_base));
    assert(mmap(reinterpret_cast<void*>(user_address), 2 * page_size, PROT_NONE,
                MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0) == reinterpret_cast<void*>(user_address));
    boot_info info{};
    info.reserved_low_end = physical_base;
    info.region_count = 1;
    memory_region region{physical_base, physical_bytes, memory_kind::usable, 0};
    memory_init(info, &region);
    u64 pdpt, pd;
    assert(allocate_page(&host_active_cr3) == memory_result::none);
    assert(allocate_page(&pdpt) == memory_result::none && allocate_page(&pd) == memory_result::none);
    reinterpret_cast<u64*>(host_active_cr3)[0] = pdpt | 3;
    reinterpret_cast<u64*>(pdpt)[0] = pd | 3;
    const u64 bootstrap = host_active_cr3;
    const u32 baseline = memory_status().allocated_pages;

    device_backend.authorized = device_grant_allowed;
    device_backend.inspect = device_description;
    for (u32 scenario = 0; scenario < 6; ++scenario) {
        owner = {};
        caller = {};
        owner.pid = 1;
        owner.cr3 = create_address_space();
        const u64 child = create_address_space();
        assert(owner.cr3 && child);
        caller.process = &owner;
        caller.state = thread_state::running;
        u64 originals[2]{};
        for (u32 i = 0; i < 2; ++i) {
            assert(allocate_user_page(&originals[i]) == memory_result::none);
            auto* bytes = reinterpret_cast<u8*>(originals[i]);
            for (u32 j = 0; j < page_size; ++j) { bytes[j] = 0x77; }
            assert(map_page_in(owner.cr3, user_address + i * page_size, originals[i],
                              {!(scenario == 2 && i == 1), false, true}) == memory_result::none);
            assert(cow1_stage_page(owner.cr3, child, user_address + i * page_size, nullptr) == memory_result::none);
            assert(cow1_publish_page(owner.cr3, child, user_address + i * page_size) == memory_result::none);
        }
        device_output grant{};
        constexpr u64 device_request_address = user_address + 256;
        constexpr u64 device_output_address = user_address + page_size - 24;
        if (scenario == 5) {
            assert(device_store.grant(device_backend, 2, {1, 10, device_right_query, 0}, grant) == 0);
            *reinterpret_cast<device_resource_input*>(originals[0] + 128) = {};
            device_request request{};
            request.version = 1; request.size = sizeof(request); request.operation = device_operation::query;
            request.object_token = grant.token; request.input_address = user_address + 128;
            request.input_length = sizeof(device_resource_input);
            request.output_address = device_output_address; request.output_length = sizeof(device_output);
            *reinterpret_cast<device_request*>(originals[0] + 256) = request;
        }
        u8 expected_originals[2][page_size];
        for (u32 i = 0; i < 2; ++i) {
            const auto* bytes = reinterpret_cast<const u8*>(originals[i]);
            for (u32 j = 0; j < page_size; ++j) expected_originals[i][j] = bytes[j];
        }
        host_active_cr3 = owner.cr3;
        host_invalidate(user_address);
        host_invalidate(user_address + page_size);
        pipes[0] = {};
        pipes[0].used = true;
        pipes[0].length = 32;
        pipes[0].writer_references = 1;
        for (u32 i = 0; i < 32; ++i) { pipes[0].data[i] = static_cast<u8>(i); }
        owner.stdio_mask = 1;
        owner.stdio[0] = {true, scenario == 3, false, 0};
        const u32 before = memory_status().allocated_pages;
        if (scenario == 0 || scenario == 1) {
            memory_self_test_fail_after(1);
            assert(invoke(sys_read, []() { return stdio_read(current, 0, user_address + page_size - 16, 32, false); }) == process_error_resources);
            memory_self_test_fail_after(-1);
            assert(memory_status().allocated_pages == before && pipes[0].length == 32 && pipes[0].head == 0);
            assert(user_page_references(originals[0]) == 2 && user_page_references(originals[1]) == 2);
            if (scenario == 0) {
                assert(invoke(sys_read, []() { return stdio_read(current, 0, user_address + page_size - 16, 32, false); }) == 32);
                assert(pipes[0].length == 0);
            } else {
                endpoints[0] = {};
                endpoints[0].used = endpoints[0].pending = true;
                endpoints[0].handle = owner.recv_handle = 1;
                endpoints[0].receiver_pid = 1;
                endpoints[0].length = 32;
                for (u32 i = 0; i < 32; ++i) { endpoints[0].data[i] = static_cast<u8>(i); }
                memory_self_test_fail_after(1);
                assert(invoke(sys_recv, []() { return ipc_recv(1, user_address + page_size - 16, 32); }) == sys_error_full);
                memory_self_test_fail_after(-1);
                assert(endpoints[0].pending && endpoints[0].length == 32 && memory_status().allocated_pages == before);
                assert(invoke(sys_recv, []() { return ipc_recv(1, user_address + page_size - 16, 32); }) == 32);
                assert(!endpoints[0].pending);
            }
            const auto* output = reinterpret_cast<const u8*>(user_address + page_size - 16);
            for (u32 i = 0; i < 32; ++i) { assert(output[i] == i); }
        } else if (scenario == 2) {
            assert(invoke(sys_read, []() { return stdio_read(current, 0, user_address + page_size - 16, 32, false); }) == process_error_invalid);
            assert(pipes[0].length == 32 && memory_status().allocated_pages == before);
        } else if (scenario == 3) {
            memory_self_test_fail_after(0);
            assert(invoke(sys_read, []() { return stdio_read(current, 0, user_address, 1, false); }) == process_error_resources);
            memory_self_test_fail_after(-1);
            assert(console_reads == 0 && memory_status().allocated_pages == before);
        } else if (scenario == 4) {
            memory_self_test_fail_after(0);
            assert(invoke(sys_random_bytes, []() { return random_bytes(user_address, 32); }) == random_error_io);
            memory_self_test_fail_after(-1);
            assert(memory_status().allocated_pages == before);
        } else {
            memory_self_test_fail_after(1);
            assert(invoke(sys_device, nullptr, device_request_address) == device_resources);
            memory_self_test_fail_after(-1);
            assert(memory_status().allocated_pages == before && !caller.ipc_v1_pins[0].active());
            assert(user_page_references(originals[0]) == 2 && user_page_references(originals[1]) == 2);
            assert(invoke(sys_device, nullptr, device_request_address) == 0);
            const auto& output = *reinterpret_cast<const device_output*>(device_output_address);
            assert(output.token == grant.token && output.length == 16384 && output.address == 0);
            assert(output.attributes == (device_attribute_mmio | device_attribute_uncached));
            assert(!caller.ipc_v1_pins[0].active());
        }
        for (u32 i = 0; i < 2; ++i) {
            const auto* bytes = reinterpret_cast<const u8*>(originals[i]);
            for (u32 j = 0; j < page_size; ++j) { assert(bytes[j] == expected_originals[i][j]); }
        }
        host_active_cr3 = bootstrap;
        destroy_address_space(owner.cr3);
        destroy_address_space(child);
        assert(user_pages_status().unique_pages == 0 && memory_status().allocated_pages == baseline);
    }
    assert(munmap(reinterpret_cast<void*>(user_address), 2 * page_size) == 0);
    assert(munmap(reinterpret_cast<void*>(physical_base), physical_bytes) == 0);
    assert(close(physical_fd) == 0);
    std::puts("PASS real pipe/stdio/recv/random/device copyout: cross-page OOM, read-only tail, queue/input preservation, errno, device pin release, parent-child isolation and cleanup");
}
