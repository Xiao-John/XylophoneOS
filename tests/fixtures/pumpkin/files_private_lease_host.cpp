// SPDX-License-Identifier: Apache-2.0
#include "services/files_private_broker.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>

using namespace xos;
using namespace xos::user::files_private_storage;

namespace {
constexpr u32 root_request = 101, root_response = 102;
constexpr u64 root_pid = 7, direct_child = 20, unrelated_child = 21, second_child = 22;
constexpr u64 getpid_syscall = 6;
constexpr u64 receive_syscall = 5;

struct kernel_fixture {
    file_session_info sessions[4]{
        {root_pid, 0, root_request, root_response},
        {direct_child, root_pid, 200, 201},
        {unrelated_child, 30, 202, 203},
        {second_child, root_pid, 204, 205},
    };
    u64 endpoint_peer = 0;
    i64 clock = 1;
    i64 readiness = 0;
    u32 next = 300;
    u32 created = 0;
    u32 closed = 0;
} kernel;

struct backend {
    u8 slots[slot_count][slot_bytes]{};
    u32 writes = 0;
    bool sync_fails = false;
    bool bad_readback = false;

    slot_io io() {
        return {this,
                [](void* context, u32 slot, u8 (&data)[slot_bytes]) {
                    auto& self = *static_cast<backend*>(context);
                    std::memcpy(data, self.slots[slot], sizeof(data));
                    if (self.bad_readback) {
                        data[0] ^= 1;
                    }
                    return true;
                },
                [](void* context, u32 slot, const u8 (&data)[slot_bytes]) {
                    auto& self = *static_cast<backend*>(context);
                    ++self.writes;
                    std::memcpy(self.slots[slot], data, sizeof(data));
                    return !self.sync_fails;
                }};
    }
};

struct caller {
    u32 binding;
    u64 sequence = 0;

    response call(slot_lease& lease, operation op, u32 offset = 0, u32 length = 0) {
        request message;
        message.sequence = ++sequence;
        message.op = op;
        message.offset = offset;
        message.length = length;
        if (op == operation::chunk) {
            std::memset(message.data, offset == 0 ? 0x53 : 0x97, length);
        }
        response output;
        assert(lease.dispatch(binding, message, output));
        assert(output.sequence == sequence && output.op == op);
        return output;
    }
};

void test_exclusion() {
    backend device;
    slot_lease lease(device.io());
    assert(!lease.acquire(0, access::writer));
    caller reader{10};
    assert(lease.acquire(reader.binding, access::reader));
    assert(!lease.acquire(20, access::reader) && !lease.acquire(21, access::writer));
    lease.release(11);
    assert(lease.occupied());
    auto output = reader.call(lease, operation::begin);
    assert(output.status == result::denied && output.length == 0 && device.writes == 0);
    output = reader.call(lease, operation::read, 0, payload_bytes);
    assert(output.status == result::ok && output.length == payload_bytes);
    lease.release(reader.binding);
    assert(!lease.occupied());

    assert(lease.acquire(20, access::writer));
    request stale;
    stale.op = operation::read;
    stale.sequence = 1;
    stale.length = 1;
    assert(!lease.dispatch(reader.binding, stale, output));
    assert(lease.dispatch(20, stale, output));
    assert(!lease.dispatch(20, stale, output));
}

void test_staging() {
    backend device;
    slot_lease lease(device.io());
    caller first{10};
    assert(lease.acquire(first.binding, access::writer));
    assert(first.call(lease, operation::begin).status == result::ok);
    assert(first.call(lease, operation::chunk, 0, payload_bytes).status == result::ok);
    assert(first.call(lease, operation::commit).status == result::invalid);
    assert(first.call(lease, operation::read, 0, 1).status == result::busy);
    assert(device.writes == 0);
    lease.release(first.binding);

    caller next{20};
    assert(lease.acquire(next.binding, access::writer));
    assert(next.call(lease, operation::commit).status == result::invalid);
    assert(next.call(lease, operation::begin).status == result::ok);
    assert(next.call(lease, operation::chunk, payload_bytes, payload_bytes).status == result::invalid);
    assert(next.call(lease, operation::chunk, 0, payload_bytes).status == result::ok);
    assert(next.call(lease, operation::chunk, payload_bytes, payload_bytes).status == result::ok);
    assert(next.call(lease, operation::commit).status == result::ok);
    assert(device.writes == 1 && device.slots[0][0] == 0x53 && device.slots[0][slot_bytes - 1] == 0x97);
    const auto observed = next.call(lease, operation::read, payload_bytes, payload_bytes);
    assert(observed.status == result::ok && observed.length == payload_bytes &&
           observed.data[payload_bytes - 1] == 0x97);
}

void test_uncertain(bool sync_fails) {
    backend device;
    device.sync_fails = sync_fails;
    device.bad_readback = !sync_fails;
    slot_lease lease(device.io());
    caller writer{10};
    assert(lease.acquire(writer.binding, access::writer));
    assert(writer.call(lease, operation::begin).status == result::ok);
    assert(writer.call(lease, operation::chunk, 0, payload_bytes).status == result::ok);
    assert(writer.call(lease, operation::chunk, payload_bytes, payload_bytes).status == result::ok);
    const auto outcome = writer.call(lease, operation::commit);
    assert(outcome.status == result::outcome_unknown && outcome.length == 0);
}

void test_boot_binding() {
    backend device;
    broker service(device.io());
    assert(service.establish_bootstrap());
    const auto root = kernel.sessions[0];
    auto forged = root;
    forged.request_handle = 200;
    grant_request request;
    request.child = direct_child;
    request.rights = access::writer;
    assert(service.grant(request, forged, 0, true).status == result::invalid);
    assert(service.grant(request, root, 1, true).status == result::invalid);
    request.child = unrelated_child;
    assert(service.grant(request, root, 0, true).status == result::denied && kernel.created == 0);
    request.child = direct_child;
    const auto first = service.grant(request, root, 0, true);
    assert(first.status == result::ok && first.channel.send == 301 && first.channel.receive == 300);
    request.rights = access::reader;
    request.child = second_child;
    assert(service.grant(request, root, 0, true).status == result::busy && kernel.created == 1);

    // Successful exec / close manifests as loss of the old kernel pair.
    kernel.readiness = process_error_denied;
    service.poll(true);
    assert(kernel.closed == 2);
    kernel.readiness = 0;
    const auto second = service.grant(request, root, 0, true);
    assert(second.status == result::ok && second.channel.send != first.channel.send);
    kernel.sessions[0] = {};
    service.poll(true);
    assert(kernel.closed == 4);
    assert(service.grant(request, root, 0, true).status == result::invalid);
}

void test_lease_duration(lease_profile profile, u64 duration) {
    kernel = {};
    backend device;
    broker service(device.io(), profile);
    assert(service.establish_bootstrap());
    const auto root = kernel.sessions[0];
    const grant_request request{grant_magic, protocol_version, direct_child, access::writer, 0};
    assert(service.grant(request, root, 0, true).status == result::ok);

    kernel.clock = static_cast<i64>(duration);
    service.poll(true);
    assert(kernel.closed == 0);
    ++kernel.clock;
    service.poll(true);
    assert(kernel.closed == 2);

    assert(service.grant(request, root, 0, true).status == result::ok);
    kernel.sessions[0] = {};
    service.poll(true);
    assert(kernel.closed == 4);
}
}

i64 xos::sdk::syscall(u64 number, u64 first, u64 second, u64 third) {
    switch (number) {
    case sys_ipc_handles: {
        const u32 handles[]{root_response, root_request};
        std::memcpy(reinterpret_cast<void*>(first), handles, sizeof(handles));
        return 0;
    }
    case sys_file_session: {
        const file_session_info empty{};
        const auto& value = first < 4 ? kernel.sessions[first] : empty;
        std::memcpy(reinterpret_cast<void*>(second), &value, sizeof(value));
        return 0;
    }
    case sys_ipc_endpoint:
        if (first == static_cast<u64>(ipc_endpoint_action::create)) {
            kernel.endpoint_peer = second;
            const ipc_channel pair{kernel.next, kernel.next + 1};
            kernel.next += 2;
            ++kernel.created;
            std::memcpy(reinterpret_cast<void*>(third), &pair, sizeof(pair));
        } else if (first == static_cast<u64>(ipc_endpoint_action::query_peer)) {
            std::memcpy(reinterpret_cast<void*>(third), &kernel.endpoint_peer, sizeof(kernel.endpoint_peer));
        } else {
            assert(first == static_cast<u64>(ipc_endpoint_action::close));
            ++kernel.closed;
        }
        return 0;
    case sys_clock_monotonic: return kernel.clock;
    case sys_ipc_wait: return kernel.readiness;
    case getpid_syscall: return 8;
    case receive_syscall: return process_error_would_block;
    default:
        assert(false);
        return -1;
    }
}

int main() {
    test_exclusion();
    std::puts("PASS exclusive reader/writer lifecycle and stale binding rejection");
    test_staging();
    std::puts("PASS partial writes stay in memory and later lease verifies full slot");
    test_uncertain(true);
    test_uncertain(false);
    std::puts("PASS sync/readback failures return outcome unknown");
    test_boot_binding();
    std::puts("PASS boot-pair and actual target-parent checks with endpoint cleanup");
    test_lease_duration(lease_profile::short_operation, 30'000'000'000ull);
    test_lease_duration(lease_profile::desktop, 31ull * 60 * 1'000'000'000);
    test_lease_duration(lease_profile::launch_acceptance, 300'000'000'000ull);
    std::puts("PASS short, desktop and explicit launch deadlines remain bounded and revoke with the controller");
}
