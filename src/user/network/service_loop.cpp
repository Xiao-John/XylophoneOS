// SPDX-License-Identifier: Apache-2.0
#include "service_loop.hpp"
#include "service_core.hpp"
#include "lwip_stack.hpp"
#include <xos/net_abi.hpp>
#include <xos/sdk.hpp>
#include <xos/thread_abi.hpp>
#ifdef XOS_NET_DHCP_PROFILE
#include "xos_net_dhcp_profile.hpp"
#endif
#ifdef XOS_NET_EGRESS_PROFILE
#include "xos_net_egress_profile.hpp"
#endif

namespace xos::user::network {
namespace {
struct ipc_session {
    ipc_channel channel;
    net2::message reply;
    u64 reply_deadline, generation;
    bool pending, delivered;
    u32 reply_bytes;
} sessions[net2::session_limit];
service_core core;
lwip_stack stack;
net2::message incoming;
u64 bounded_deadline(u64 now, u64 duration) {
    return now > ~u64{0} - duration ? ~u64{0} : now + duration;
}
void close_channel(ipc_channel& channel) {
    if (channel.send) (void)sdk::ipc_channel_close(channel.send);
    if (channel.receive) (void)sdk::ipc_channel_close(channel.receive);
    channel = {};
}
void clear_session(u32 slot) {
    close_channel(sessions[slot].channel);
    sessions[slot] = {};
}
void drop(u32 slot) {
    // A transport binding must never detach a replacement generation.
    if (sessions[slot].generation == core.generation(slot)) core.detach(slot);
    clear_session(slot);
}
}
frame_io network_frame_io(virtio_net::driver& nic) {
    return {&nic,
        [](void* context, u8* data, u32 capacity) { return static_cast<virtio_net::driver*>(context)->receive(data, capacity); },
        [](void* context, const u8* data, u32 length) {
            const i64 result = static_cast<virtio_net::driver*>(context)->transmit(data, length);
            return result == device_busy ? net2::would_block : result; },
        [](void*) { return sdk::syscall(sys_clock_monotonic); },
        [](void*, u32& value) { return sdk::syscall(sys_random_bytes, reinterpret_cast<u64>(&value), sizeof(value)); },
        [](void* context) { return static_cast<virtio_net::driver*>(context)->link_state(); }};
}
i64 serve(u64 controller, virtio_net::driver& nic) {
    i64 result = stack.initialize(network_frame_io(nic), nic.mac());
    if (result) { stack.shutdown(); return result; }
#ifdef XOS_NET_EGRESS_PROFILE
    const auto& application_policy = installed_egress_policy;
#else
    const auto& application_policy = default_egress_policy;
#endif
#ifdef XOS_NET_STATIC_RESOLVER
    core.initialize(controller, stack.api(), stack.dns_api(), XOS_NET_STATIC_RESOLVER, application_policy,
                    XOS_NET_SECONDARY_RESOLVER);
#else
    core.initialize(controller, stack.api(), stack.dns_api(), 0, application_policy);
#endif
#ifdef XOS_NET_DHCP_PROFILE
    core.enable_dhcp();
    result = stack.start_dhcp(installed_dhcp_policy, installed_acquisition_ns,
        [](void*, u32 address, u32 mask, u32 gateway, u32 resolver, u32 secondary) {
            for (u32 slot = 0; slot < net2::client_sessions; ++slot) clear_session(slot);
            return core.publish_dhcp(address, mask, gateway, resolver, secondary);
        }, nullptr);
    if (result) { stack.shutdown(); return result; }
#endif
    result = sdk::ipc_name_publish(net2::service_name);
    if (result) { stack.shutdown(); return result; }
    result = sdk::ipc_name_publish(net::service_name);
    if (result) { (void)sdk::ipc_name_unpublish(net2::service_name); stack.shutdown(); return result; }
    sdk::print("[net] ready native_v2=1 user_driver=1 lwip=2.2.1 sessions=4 raw_ethernet=0\n");
    u32 round_robin = 0;
    u64 stop_deadline = 0;
    for (;;) {
        result = stack.poll(); if (result) break;
        const i64 clock = sdk::syscall(sys_clock_monotonic);
        if (clock < 0) { result = net2::io; break; }
        u64 now = static_cast<u64>(clock);
        core.expire(now);
        bool replies_pending = false;
        for (u32 count = 0; count < net2::session_limit; ++count) {
            const u32 slot = (round_robin + count) % net2::session_limit;
            auto& session = sessions[slot];
            if (!session.channel.send) continue;
            if (!core.alive(slot) || session.generation != core.generation(slot)) { drop(slot); continue; }
            // try_send also detects process exit/exec/revocation even while idle.
            const i64 ready = sdk::ipc_wait(session.channel.send, ipc_wait_mode::try_send);
            if (ready && ready != process_error_would_block) { drop(slot); continue; }
            const i64 reply_clock = sdk::syscall(sys_clock_monotonic);
            if (reply_clock < 0) { result = net2::io; break; }
            now = static_cast<u64>(reply_clock);
#ifdef XOS_NET_DHCP_PROFILE
            if (stack.advance_dhcp()) { result = net2::io; break; }
            if (!session.channel.send || !core.alive(slot) || session.generation != core.generation(slot)) continue;
#endif
            if (session.pending) {
                if (now >= session.reply_deadline) { drop(slot); continue; }
                if (!session.delivered) {
                    const i64 sent = sdk::ipc_send(session.channel.send, &session.reply, session.reply_bytes);
                    if (!sent) session.delivered = true;
                    else if (sent != ipc_error_full) { drop(slot); continue; }
                } else if (!ready) { session.pending = session.delivered = false; }
                replies_pending |= session.pending;
                continue;
            }
            if (core.stopping()) continue;
            const i64 received = sdk::ipc_recv(session.channel.receive, &incoming, sizeof(incoming));
            if (received == -3) continue;
            if (received < static_cast<i64>(net::header_bytes)) { drop(slot); continue; }
            // Polling, other sessions and ipc_recv can cross a deadline. Sample
            // at authorization, after the complete request has been received.
            const i64 request_clock = sdk::syscall(sys_clock_monotonic);
            if (request_clock < 0) { result = net2::io; break; }
            now = static_cast<u64>(request_clock);
#ifdef XOS_NET_DHCP_PROFILE
            if (stack.advance_dhcp()) { result = net2::io; break; }
            if (!session.channel.send || !core.alive(slot) || session.generation != core.generation(slot)) continue;
#endif
            if (incoming.version == net::version) {
                net::message legacy{};
                __builtin_memcpy(&legacy, &incoming, net::header_bytes);
                if (core.peer(slot) != controller || received != net::header_bytes ||
                    legacy.action != net::operation::stop || !legacy.sequence || legacy.result ||
                    legacy.reserved || legacy.length) { drop(slot); continue; }
                net2::message request{};
                request.version = net2::version; request.action = net2::operation::stop;
                request.sequence = 1; request.deadline = bounded_deadline(now, net2::reply_timeout_ns);
                if (!core.dispatch(slot, request, net2::header_bytes, now, session.reply)) { drop(slot); continue; }
                const i64 stopped = session.reply.result;
                session.reply = {};
                net::message legacy_reply{};
                legacy_reply.version = net::version; legacy_reply.action = net::operation::stop;
                legacy_reply.sequence = legacy.sequence; legacy_reply.result = stopped;
                __builtin_memcpy(&session.reply, &legacy_reply, net::header_bytes);
                session.reply_bytes = net::header_bytes;
            } else {
                if (!core.dispatch(slot, incoming, static_cast<u32>(received), now, session.reply)) { drop(slot); continue; }
                session.reply_bytes = net2::header_bytes + session.reply.length;
            }
#ifdef XOS_NET_DHCP_PROFILE
            if (stack.advance_dhcp()) { result = net2::io; break; }
            if (!session.channel.send || !core.alive(slot) || session.generation != core.generation(slot)) continue;
#endif
            session.pending = true; session.delivered = false;
            session.reply_deadline = bounded_deadline(now, net2::reply_timeout_ns); replies_pending = true;
        }
        if (result) break;
        round_robin = (round_robin + 1) % net2::session_limit;
        if (core.stopping()) {
            if (!stop_deadline) stop_deadline = bounded_deadline(now, net2::reply_timeout_ns);
            if (!replies_pending || now >= stop_deadline) break;
        } else {
            // Bound admission work, including rejected peers, under a flood.
            for (u32 i = 0; i < net2::session_limit; ++i) {
                ipc_channel channel{};
                const i64 accepted = sdk::ipc_name_try_accept(channel);
                if (accepted == process_error_would_block) break;
                if (accepted) { result = accepted; break; }
                u64 send_peer = 0, receive_peer = 0;
                const bool authenticated = !sdk::ipc_endpoint_peer(channel.send, send_peer) &&
                    !sdk::ipc_endpoint_peer(channel.receive, receive_peer) && send_peer && send_peer == receive_peer;
                const i64 slot = authenticated ? core.attach(send_peer, now) : net2::denied;
                if (slot < 0) close_channel(channel);
                else {
                    const u32 index = static_cast<u32>(slot);
                    // Revocation can free a slot after its turn this round.
                    // Close both old endpoints and erase reply state before
                    // binding the newly authenticated application. Do not
                    // detach the generation which attach just created.
                    clear_session(index);
                    sessions[index].channel = channel;
                    sessions[index].generation = core.generation(index);
                }
            }
            if (result) break;
        }
        result = nic.wait(bounded_deadline(now, thread_tick_ns));
        if (result == device_timeout) result = 0;
        if (result) break;
    }
    (void)sdk::ipc_name_unpublish(net2::service_name);
    (void)sdk::ipc_name_unpublish(net::service_name);
    core.shutdown();
    for (u32 i = 0; i < net2::session_limit; ++i) clear_session(i);
    stack.shutdown(); return result;
}
}
