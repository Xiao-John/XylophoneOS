// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/net_service_abi.hpp>
#include <xos/sdk.hpp>
#include <xos/thread_abi.hpp>

namespace xos::net2 {
inline constexpr char service_pid_variable[] = "XOS_NET_SERVICE_PID";

class session_client {
public:
    session_client() = default;
    session_client(const session_client&) = delete;
    session_client& operator=(const session_client&) = delete;
    ~session_client() { close(); }
    i64 connect(u64 expected_service_pid) {
        if (!expected_service_pid) return invalid;
        if (channel_.send) return resources;
        const i64 result = sdk::ipc_name_connect(service_name, channel_);
        if (result) { close(); return closed; }
        u64 send_peer = 0, receive_peer = 0;
        if (sdk::ipc_endpoint_peer(channel_.send, send_peer) || sdk::ipc_endpoint_peer(channel_.receive, receive_peer) ||
            send_peer != expected_service_pid || receive_peer != expected_service_pid) {
            close(); return denied;
        }
        peer_pid_ = expected_service_pid;
        return 0;
    }
    void close() {
        if (channel_.send) (void)sdk::ipc_channel_close(channel_.send);
        if (channel_.receive) (void)sdk::ipc_channel_close(channel_.receive);
        channel_ = {}; next_sequence_ = 1; peer_pid_ = 0;
    }
    // Read-only provenance of the current kernel-authenticated connection.
    u64 authenticated_service_pid() const { return peer_pid_; }
    i64 request(message& input, message& reply) {
        reply = {};
        if (!channel_.send || !next_sequence_ || input.length > payload_bytes || input.reserved || input.result) return invalid;
        const i64 began = sdk::syscall(sys_clock_monotonic);
        if (began < 0) { close(); return io; }
        if (input.deadline <= static_cast<u64>(began) || input.deadline - static_cast<u64>(began) > max_request_ns) {
            close(); return timeout;
        }
        input.version = version; input.sequence = next_sequence_++;
        const bool assigns_object = input.action == operation::open || input.action == operation::resolve_start;
        bool sent = false;
        for (;;) {
            const i64 clock = sdk::syscall(sys_clock_monotonic);
            if (clock < 0) { close(); return io; }
            const u64 now = static_cast<u64>(clock);
            if (now >= input.deadline) { close(); return timeout; }
            if (!sent) {
                const i64 result = sdk::ipc_send(channel_.send, &input, header_bytes + input.length);
                if (!result) sent = true;
                else if (result != ipc_error_full) { close(); return closed; }
            }
            if (sent) {
                const i64 received = sdk::ipc_recv(channel_.receive, &reply, sizeof(reply));
                if (received == -1 || received == ipc_error_broken) { reply = {}; close(); return closed; }
                if (received != -3) {
                    const i64 finished = sdk::syscall(sys_clock_monotonic);
                    if (finished < 0 || static_cast<u64>(finished) >= input.deadline) {
                        reply = {}; close(); return finished < 0 ? io : timeout;
                    }
                    if (received < header_bytes || reply.version != version || reply.action != input.action ||
                        reply.sequence != input.sequence || reply.deadline || reply.reserved || reply.address ||
                        reply.port || reply.transport != protocol::none || reply.length > payload_bytes ||
                        static_cast<u64>(received) != header_bytes + reply.length ||
                        (reply.result < 0 && reply.length) || !valid_reply(input, reply) ||
                        (!assigns_object && reply.object != input.object) ||
                        (assigns_object && ((reply.result == 0) != (reply.object != 0))) ||
                        (reply.result > 0 && (input.action != operation::send || static_cast<u64>(reply.result) > input.length))) {
                        reply = {}; close(); return io;
                    }
                    return reply.result;
                }
            }
            const u64 next = input.deadline - now < thread_tick_ns ? input.deadline : now + thread_tick_ns;
            if (sdk::syscall(sys_sleep_until, next)) { close(); return io; }
        }
    }
    i64 configuration(u64 deadline, config_snapshot& snapshot) {
        message input{}, reply{};
        input.action = operation::configuration; input.deadline = deadline;
        const i64 result = request(input, reply);
        snapshot = {};
        if (!result) __builtin_memcpy(&snapshot, reply.data, sizeof(snapshot));
        return result;
    }
    i64 lease_status(u64 deadline, lease_snapshot& snapshot) {
        message input{}, reply{};
        input.action = operation::lease_status; input.deadline = deadline;
        const i64 result = request(input, reply);
        snapshot = {};
        if (!result) __builtin_memcpy(&snapshot, reply.data, sizeof(snapshot));
        return result;
    }
    i64 capabilities(u64 deadline, capability_snapshot& snapshot) {
        message input{}, reply{};
        input.action = operation::capabilities; input.deadline = deadline;
        const i64 result = request(input, reply);
        snapshot = {};
        if (!result) __builtin_memcpy(&snapshot, reply.data, sizeof(snapshot));
        return result;
    }
    i64 peer_policy(peer_policy_action action, u64 retired_pid, u64 deadline, peer_policy_snapshot& snapshot) {
        message input{}, reply{};
        const peer_policy_request requested{peer_policy_revision, sizeof(peer_policy_request), action, 0};
        input.action = operation::peer_policy; input.object = retired_pid;
        input.deadline = deadline; input.length = sizeof(requested);
        __builtin_memcpy(input.data, &requested, sizeof(requested));
        const i64 result = request(input, reply);
        snapshot = {};
        if (!result) __builtin_memcpy(&snapshot, reply.data, sizeof(snapshot));
        return result;
    }
    i64 readiness(u64 handle, u64 deadline, readiness_snapshot& snapshot) {
        message input{}, reply{};
        input.action = operation::readiness; input.object = handle; input.deadline = deadline;
        const i64 result = request(input, reply);
        snapshot = {};
        if (!result) __builtin_memcpy(&snapshot, reply.data, sizeof(snapshot));
        return result;
    }
    i64 shutdown_write(u64 handle, u64 deadline) {
        message input{}, reply{};
        input.action = operation::shutdown_write; input.object = handle; input.deadline = deadline;
        return request(input, reply);
    }
    i64 configure(network_mode mode, u64 epoch, u64 deadline, config_snapshot& snapshot) {
        message input{}, reply{};
        const config_request config{configuration_revision, mode, epoch};
        input.action = operation::configure; input.deadline = deadline; input.length = sizeof(config);
        __builtin_memcpy(input.data, &config, sizeof(config));
        const i64 result = request(input, reply);
        snapshot = {};
        if (!result) __builtin_memcpy(&snapshot, reply.data, sizeof(snapshot));
        return result;
    }
    i64 resolve_start(const char* name, u32 length, u64 deadline, u64& ticket) {
        ticket = 0;
        if (!name || !length || length > dns_name_limit + 1) return invalid;
        message input{}, reply{};
        input.action = operation::resolve_start; input.deadline = deadline; input.length = length;
        __builtin_memcpy(input.data, name, length);
        const i64 result = request(input, reply);
        if (!result) ticket = reply.object;
        return result;
    }
    i64 resolve_result(u64 ticket, u64 deadline, resolve_reply& answer) {
        message input{}, reply{};
        input.action = operation::resolve_result; input.deadline = deadline; input.object = ticket;
        const i64 result = request(input, reply);
        answer = {};
        if (!result) __builtin_memcpy(&answer, reply.data, sizeof(answer));
        return result;
    }
    i64 resolve_cancel(u64 ticket, u64 deadline) {
        message input{}, reply{};
        input.action = operation::resolve_cancel; input.deadline = deadline; input.object = ticket;
        return request(input, reply);
    }
private:
    static bool valid_reply(const message& input, const message& reply) {
        if (reply.result < 0) {
            const bool n4 = input.action >= operation::configuration && input.action <= operation::resolve_cancel;
            if (reply.result < (n4 ? dns_expired : reset) || reply.result > invalid) return false;
            if (input.action == operation::open || input.action == operation::status)
                return !reply.flags || reply.flags == failed;
            if (input.action == operation::receive && reply.result == buffer_too_small)
                return reply.flags > input.flags && reply.flags <= payload_bytes;
            return !reply.flags;
        }
        switch (input.action) {
        case operation::peer_policy: {
            if (reply.result || reply.length != sizeof(peer_policy_snapshot) || reply.flags) return false;
            peer_policy_snapshot snapshot{};
            __builtin_memcpy(&snapshot, reply.data, sizeof(snapshot));
            return snapshot.revision == peer_policy_revision && snapshot.size == sizeof(snapshot) &&
                snapshot.capacity == revoked_peer_limit && snapshot.occupied <= snapshot.capacity;
        }
        case operation::information:
            return !reply.result && reply.length == sizeof(information) && !reply.flags;
        case operation::open:
        case operation::status:
            return !reply.result && !reply.length &&
                (reply.flags == connecting || reply.flags == connected || reply.flags == (connected | eof));
        case operation::send:
            return !reply.length && !reply.flags && (!input.length || reply.result > 0);
        case operation::receive:
            return !reply.result && reply.length <= input.flags && !(reply.flags & ~eof);
        case operation::close:
        case operation::cancel:
        case operation::revoke_peer:
        case operation::stop:
        case operation::resolve_start:
        case operation::resolve_cancel:
        case operation::shutdown_write:
            return !reply.result && !reply.length && !reply.flags;
        case operation::capabilities: {
            if (reply.result || reply.length != sizeof(capability_snapshot) || reply.flags) return false;
            capability_snapshot snapshot{};
            __builtin_memcpy(&snapshot, reply.data, sizeof(snapshot));
            return snapshot.revision == socket_extension_revision && !snapshot.reserved &&
                !(snapshot.flags & ~(capability_readiness | capability_shutdown_write));
        }
        case operation::readiness: {
            if (reply.result || reply.length != sizeof(readiness_snapshot) || reply.flags) return false;
            readiness_snapshot snapshot{};
            __builtin_memcpy(&snapshot, reply.data, sizeof(snapshot));
            return snapshot.generation && !snapshot.reserved && !(snapshot.events & ~ready_all) &&
                snapshot.readable_bytes <= tcp_receive_bytes &&
                ((snapshot.error < 0 && snapshot.error >= reset && snapshot.error <= invalid &&
                  (snapshot.events & ready_error)) || (!snapshot.error && !(snapshot.events & ready_error))) &&
                (!snapshot.readable_bytes || (snapshot.events & ready_read)) &&
                ((snapshot.writable_bytes != 0) == ((snapshot.events & ready_write) != 0)) &&
                (!(snapshot.events & ready_eof) || ((snapshot.events & ready_read) && !snapshot.error)) &&
                (!(snapshot.events & ready_write_closed) || !(snapshot.events & ready_write));
        }
        case operation::configuration:
        case operation::configure: {
            if (reply.result || reply.length != sizeof(config_snapshot) || reply.flags) return false;
            config_snapshot config{};
            __builtin_memcpy(&config, reply.data, sizeof(config));
            return config.revision == configuration_revision && config.epoch && !config.reserved &&
                config.capabilities == resolve_in_a && config.tickets <= client_sessions &&
                ((config.mode == network_mode::dhcp &&
                  (config.address ? valid_lease_configuration(config.address, config.mask, config.gateway, config.resolver) :
                   (!config.mask && !config.gateway && !config.resolver))) ||
                 (config.address == static_address && config.mask == static_mask && config.gateway == permitted_address &&
                  ((config.mode == network_mode::disabled && !config.resolver) ||
                   (config.mode == network_mode::static_direct && valid_static_resolver(config.resolver)))));
        }
        case operation::lease_status: {
            if (reply.result || reply.length != sizeof(lease_snapshot) || reply.flags) return false;
            lease_snapshot value{};
            __builtin_memcpy(&value, reply.data, sizeof(value));
            if (value.revision != lease_revision || !value.epoch || value.reserved || !value.start_attempts || value.start_failures > value.start_attempts ||
                value.state > 8 || value.reason > 7) return false;
            if (!value.address) return value.state != 4 && value.state != 5 && value.state != 6 &&
                !value.request_sent && !value.t1 && !value.t2 && !value.expires && !value.server &&
                !value.mask && !value.gateway && !value.resolver;
            return value.state >= 3 && value.state <= 6 && unicast_ipv4(value.server) &&
                valid_lease_configuration(value.address, value.mask, value.gateway, value.resolver) &&
                value.request_sent < value.t1 && value.t1 < value.t2 && value.t2 < value.expires;
        }
        case operation::resolve_result: {
            if (reply.result || reply.length != sizeof(resolve_reply) || reply.flags) return false;
            resolve_reply answer{};
            __builtin_memcpy(&answer, reply.data, sizeof(answer));
            return answer.epoch && !answer.reserved;
        }
        default: return false;
        }
    }
    ipc_channel channel_{};
    u64 next_sequence_ = 1;
    u64 peer_pid_ = 0;
};
}
