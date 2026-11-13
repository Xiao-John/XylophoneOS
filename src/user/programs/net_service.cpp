// SPDX-License-Identifier: Apache-2.0
#include <xos/net_abi.hpp>
#include <xos/channel_io.hpp>
#include <xos/text.hpp>
#include "../drivers/virtio_net.hpp"

namespace {
using namespace xos;
user::virtio_net::driver nic;
u8 frames[8][net::frame_bytes];
u32 frame_lengths[8], receive_head, receive_count;
net::message incoming, reply;
u64 controller;

u64 now() { return static_cast<u64>(sdk::syscall(sys_clock_monotonic)); }
i64 bootstrap(u64& grant) {
    channel_info channel{};
    const i64 result = sdk::channel_get(0, channel);
    if (result || channel.rights != channel_receive || channel.peer_pid != channel.controller_pid) return device_denied;
    net::bootstrap message{};
    const i64 received = sdk::channel_receive_wait(channel.handle, &message, sizeof(message), now() + 3000000000ull);
    (void)sdk::channel_close(channel.handle);
    if (received != sizeof(message) || message.version != net::version || message.size != sizeof(message) || !message.grant)
        return device_invalid;
    grant = message.grant; controller = channel.controller_pid; return 0;
}
void result_line(const char* label, i64 value) {
    sdk::print(label); sdk::signed_decimal(value); sdk::print("\n");
}
void make_arp(u8 (&frame)[60]) {
    for (u32 i = 0; i < 6; ++i) { frame[i] = 0xff; frame[6 + i] = nic.mac()[i]; frame[22 + i] = nic.mac()[i]; }
    frame[12] = 8; frame[13] = 6; frame[15] = 1; frame[16] = 8; frame[18] = 6; frame[19] = 4; frame[21] = 1;
    frame[28] = 10; frame[30] = 2; frame[31] = 15;
    frame[38] = 10; frame[40] = 2; frame[41] = 2;
}
bool gateway_arp(const u8* frame, u32 length) {
    if (length < 42 || frame[12] != 8 || frame[13] != 6 || frame[14] || frame[15] != 1 ||
        frame[16] != 8 || frame[17] || frame[18] != 6 || frame[19] != 4 || frame[20] || frame[21] != 2 ||
        frame[28] != 10 || frame[29] || frame[30] != 2 || frame[31] != 2 ||
        frame[38] != 10 || frame[39] || frame[40] != 2 || frame[41] != 15) return false;
    for (u32 i = 0; i < 6; ++i) if (frame[32 + i] != nic.mac()[i]) return false;
    return true;
}
int probe() {
    u8 request[60]{}; make_arp(request);
    const i64 sent = nic.transmit(request, sizeof(request));
    if (sent) { result_line("[net-probe] transmit=", sent); return 4; }
    const u64 deadline = now() + 3000000000ull;
    bool received = false;
    while (!received && now() < deadline) {
        const i64 waited = nic.wait(deadline);
        if (waited && waited != device_timeout) { result_line("[net-probe] irq=", waited); return 5; }
        for (u32 i = 0; i < user::virtio_net::queue_size; ++i) {
            const i64 length = nic.receive(frames[0], sizeof(frames[0]));
            if (length < 0) { result_line("[net-probe] receive=", length); return 6; }
            if (!length) break;
            if (gateway_arp(frames[0], static_cast<u32>(length))) received = true;
        }
    }
    if (!received || !nic.irq_count()) { sdk::print("[net-probe] gateway_timeout\n"); return 7; }
    sdk::print("[net-probe] tx=1 rx_arp=1 irq="); sdk::decimal(nic.irq_count()); sdk::print("\n");
    return 0;
}
void close_session(ipc_channel& channel) {
    if (channel.send) (void)sdk::ipc_channel_close(channel.send);
    if (channel.receive) (void)sdk::ipc_channel_close(channel.receive);
    channel = {};
}
i64 serve() {
    const i64 published = sdk::ipc_name_publish(net::service_name);
    if (published) return published;
    sdk::print("[net] ready user_driver=1 raw_ethernet=1\n");
    ipc_channel channel{};
    bool pending = false, stopping = false;
    u64 peer = 0, stop_deadline = 0;
    i64 result = 0;
    for (;;) {
        for (u32 count = 0; count < user::virtio_net::queue_size; ++count) {
            const u32 index = (receive_head + receive_count) % 8;
            const i64 length = nic.receive(frames[index], sizeof(frames[index]));
            if (length < 0) { result = length; goto finished; }
            if (!length) break;
            if (receive_count == 8) { receive_head = (receive_head + 1) % 8; }
            else ++receive_count;
            frame_lengths[index] = static_cast<u32>(length);
        }
        if (pending) {
            const i64 sent = sdk::ipc_send(channel.send, &reply, net::header_bytes + reply.length);
            if (sent != -4) {
                pending = false;
                if (sent) close_session(channel);
            }
        }
        if (stopping) {
            if ((!pending && (!channel.send || sdk::ipc_wait(channel.send, ipc_wait_mode::try_send) == 0)) || now() >= stop_deadline) break;
        } else if (!channel.send) {
            const i64 accepted = sdk::ipc_name_try_accept(channel);
            if (accepted == 0 && sdk::ipc_endpoint_peer(channel.receive, peer) != 0) close_session(channel);
            else if (accepted != 0 && accepted != process_error_would_block) { result = accepted; break; }
        } else if (!pending) {
            const i64 received = sdk::ipc_recv(channel.receive, &incoming, sizeof(incoming));
            if (received != -3) {
                if (received < net::header_bytes || incoming.version != net::version || !incoming.sequence ||
                    incoming.reserved || incoming.result || incoming.length > net::frame_bytes ||
                    static_cast<u64>(received) != net::header_bytes + incoming.length) { close_session(channel); continue; }
                reply = {}; reply.version = net::version; reply.action = incoming.action; reply.sequence = incoming.sequence;
                if (incoming.action == net::operation::transmit) reply.result = nic.transmit(incoming.data, incoming.length);
                else if (incoming.length) reply.result = device_invalid;
                else if (incoming.action == net::operation::information) {
                    reply.length = 6;
                    for (u32 i = 0; i < 6; ++i) reply.data[i] = nic.mac()[i];
                } else if (incoming.action == net::operation::receive) {
                    if (!receive_count) reply.result = device_busy;
                    else {
                        reply.length = frame_lengths[receive_head];
                        for (u32 i = 0; i < reply.length; ++i) reply.data[i] = frames[receive_head][i];
                        receive_head = (receive_head + 1) % 8; --receive_count;
                    }
                } else if (incoming.action == net::operation::stop && peer == controller) {
                    stopping = true; stop_deadline = now() + 500000000ull;
                } else reply.result = device_denied;
                pending = true;
            }
        }
        const i64 waited = nic.wait(now() + thread_tick_ns);
        if (waited && waited != device_timeout) { result = waited; break; }
    }
finished:
    (void)sdk::ipc_name_unpublish(net::service_name); close_session(channel); return result;
}
}

extern "C" int xos_user_main(const xos::startup_info* startup) {
    using namespace xos;
    const auto* argv = reinterpret_cast<const char* const*>(startup->argv);
    if (startup->argc != 2 || (!sdk::equal(argv[1], "probe") && !sdk::equal(argv[1], "serve"))) return 2;
    u64 grant = 0;
    const i64 received = bootstrap(grant);
    if (received) { result_line("[net] bootstrap=", received); return 2; }
    const i64 initialized = nic.initialize(grant);
    if (initialized) { result_line("[net] initialization=", initialized); return 3; }
    const bool probing = sdk::equal(argv[1], "probe");
    const i64 result = probing ? probe() : serve();
    const i64 closed = nic.shutdown();
    result_line("[net] close=", closed);
    if (!result && !closed && probing) sdk::print("NET_USER_DRIVER_PASS\n");
    return result || closed ? 1 : 0;
}
