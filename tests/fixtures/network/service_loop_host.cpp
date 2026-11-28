// SPDX-License-Identifier: Apache-2.0
// Execute the production loop, core and pinned lwIP. Only kernel IPC/time and
// the device boundary are scheduled here; guest qualification runs separately.
#include "network/service_loop.hpp"
#include <xos/net_service_abi.hpp>
#include <xos/sdk.hpp>
#include <xos/thread_abi.hpp>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

namespace {
using namespace xos;
using namespace xos::net2;
enum class scenario { revoked_slot, expired_request };
scenario selected;
constexpr u64 controller = 77, old_peer = 101, new_peer = 102;
constexpr ipc_channel old_channel{10, 11}, control_channel{20, 21}, new_channel{30, 31};
u64 now = 1'000'000'000ull;
u32 round_number = 0, admission = 0, endpoint_closes[32]{};
bool old_requested = false, revoked = false, new_requested = false, stopped = false;
bool expired_requested = false;
std::vector<message> replies;
void expect(bool condition, const char* description) {
    if (!condition) { std::fprintf(stderr, "%s\n", description); std::abort(); }
}
message request(operation action, u64 sequence) {
    message result{};
    result.version = version; result.action = action; result.sequence = sequence;
    result.deadline = now + 100'000'000ull;
    return result;
}
i64 receive(u32 endpoint, void* destination, u64 capacity) {
    message next{};
    if (selected == scenario::revoked_slot) {
        if (endpoint == old_channel.receive && !old_requested) {
            old_requested = true;
            next = request(operation::open, 1);
            next.address = permitted_address; next.port = 9000; next.transport = protocol::udp;
        } else if (endpoint == control_channel.receive && round_number == 5 && !revoked) {
            // At round 5 the old slot (0) has already attempted its blocked
            // reply. Revocation frees it after that slot's turn, before accept.
            revoked = true;
            next = request(operation::revoke_peer, 1); next.object = old_peer;
        } else if (endpoint == new_channel.receive && !new_requested) {
            new_requested = true; next = request(operation::information, 1);
        } else if (endpoint == control_channel.receive && round_number >= 9 && !stopped) {
            stopped = true; next = request(operation::stop, 2);
        } else return process_error_would_block;
    } else {
        if (endpoint == old_channel.receive && !expired_requested) {
            expired_requested = true;
            next = request(operation::open, 1);
            next.address = permitted_address; next.port = 9000; next.transport = protocol::udp;
            // IPC receive/preemption consumes the request's remaining budget.
            now = next.deadline;
        } else if (endpoint == control_channel.receive && round_number >= 5 && !stopped) {
            stopped = true; next = request(operation::stop, 1);
        } else return process_error_would_block;
    }
    expect(capacity >= header_bytes, "loop receives a whole request envelope");
    std::memcpy(destination, &next, header_bytes); return header_bytes;
}
i64 send(u32 endpoint, const void* source, u64 length) {
    if (selected == scenario::revoked_slot && endpoint == old_channel.send) return ipc_error_full;
    if (endpoint == new_channel.send || (selected == scenario::expired_request && endpoint == old_channel.send)) {
        expect(length >= header_bytes && length <= sizeof(message), "bounded reply");
        message result{}; std::memcpy(&result, source, static_cast<usize>(length)); replies.push_back(result);
    }
    return 0;
}
}

namespace xos::sdk {
void print(const char*, u32) {}
i64 syscall(u64 number, u64 first, u64 second, u64 third) {
    if (number == 88 && first == 0) return -104; // Host loop fixture does not emulate bulk grants.
    if (number == sys_clock_monotonic) return static_cast<i64>(now);
    if (number == sys_random_bytes) {
        std::memset(reinterpret_cast<void*>(first), 0x39, static_cast<usize>(second)); return 0;
    }
    if (number == 4) return send(static_cast<u32>(first), reinterpret_cast<const void*>(second), third);
    if (number == 5) return receive(static_cast<u32>(first), reinterpret_cast<void*>(second), third);
    if (number == sys_ipc_wait) {
        expect(second == static_cast<u64>(ipc_wait_mode::try_send), "nonblocking loop wait");
        return first == old_channel.send && selected == scenario::revoked_slot ? process_error_would_block : 0;
    }
    if (number == sys_ipc_endpoint) {
        if (first == static_cast<u64>(ipc_endpoint_action::close)) {
            expect(second < 32, "known endpoint closed"); ++endpoint_closes[second]; return 0;
        }
        if (first == static_cast<u64>(ipc_endpoint_action::query_peer)) {
            const u64 peer = second == old_channel.send || second == old_channel.receive ? old_peer :
                             second == control_channel.send || second == control_channel.receive ? controller : new_peer;
            *reinterpret_cast<u64*>(third) = peer; return 0;
        }
    }
    if (number == sys_ipc_name) {
        if (first == static_cast<u64>(ipc_name_action::publish) ||
            first == static_cast<u64>(ipc_name_action::unpublish)) return 0;
        if (first == static_cast<u64>(ipc_name_action::accept)) {
            ipc_channel accepted{};
            if (admission == 0) accepted = old_channel;
            else if (admission == 1) accepted = control_channel;
            else if (admission == 2 && revoked) accepted = new_channel;
            else return process_error_would_block;
            ++admission; *reinterpret_cast<ipc_channel*>(second) = accepted; return 0;
        }
    }
    expect(false, "unexpected syscall in production service loop"); return io;
}
}
namespace xos::user::virtio_net {
i64 driver::receive(u8*, u32) { return 0; }
i64 driver::transmit(const u8*, u32) { return 0; }
i64 driver::wait(u64) {
    ++round_number; now += 1'000'000ull;
    expect(round_number <= 20, "service loop makes bounded progress"); return device_timeout;
}
}
int main(int argc, char** argv) {
    if (argc != 2) return 2;
    if (std::strcmp(argv[1], "--list") == 0) {
        std::puts("revoked_slot_reply_isolation\nexpired_request_after_receive"); return 0;
    }
    if (std::strcmp(argv[1], "revoked_slot_reply_isolation") == 0) selected = scenario::revoked_slot;
    else if (std::strcmp(argv[1], "expired_request_after_receive") == 0) selected = scenario::expired_request;
    else return 2;
    xos::user::virtio_net::driver driver;
    expect(xos::user::network::serve(controller, driver) == 0, "controller stops the real production loop");
    expect(replies.size() == 1, "exactly one reply belongs to the requesting application");
    const auto& reply = replies.front();
    expect(reply.sequence == 1, "reply has its application's sequence");
    if (selected == scenario::revoked_slot) {
        expect(reply.action == operation::information && reply.result == 0 && !reply.object,
               "reused slot must never deliver the previous application's pending OPEN reply");
        expect(reply.length == sizeof(information), "new application gets only its requested information");
        information info{}; std::memcpy(&info, reply.data, sizeof(info));
        expect(info.connections == 0, "revocation reclaimed the old application's PCB");
        expect(new_requested, "new application request was actually dispatched");
        expect(endpoint_closes[new_channel.send] == 1 && endpoint_closes[new_channel.receive] == 1,
               "new endpoints closed exactly once");
    } else {
        expect(reply.action == operation::open && reply.result == timeout && !reply.object && !reply.length,
               "deadline crossed during request receive prevents backend OPEN");
    }
    expect(endpoint_closes[old_channel.send] == 1 && endpoint_closes[old_channel.receive] == 1,
           "old endpoints reclaimed exactly once even when their slot was reused");
    expect(endpoint_closes[control_channel.send] == 1 && endpoint_closes[control_channel.receive] == 1,
           "controller endpoints closed exactly once");
    std::printf("NET_SERVICE_LOOP_CASE_PASS=%s\n", argv[1]); return 0;
}
