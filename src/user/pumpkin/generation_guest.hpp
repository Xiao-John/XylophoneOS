// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "anchored_files_store.hpp"
#include <xos/channel_io.hpp>

namespace xos::user::pumpkin::anchor_guest {

inline constexpr u32 magic = 0x31414b50; // PKA1
inline constexpr u16 version = 1;
inline constexpr u64 exchange_ns = 6'000'000'000;
enum class operation : u8 { ready = 1, read, publish, finish };
enum class scenario : u8 {
    cycle = 1, healthy, stale, user_enroll, user_login, user_revoke, user_resource, named_empty,
    user_named_read, user_named_put, user_named_erase, user_named_import, user_desktop, user_desktop_admin,
    provisioning_update, provisioning_reject, provisioning_unknown, provisioning_new,
    catalog_initial = 20, catalog_old, catalog_switch, catalog_new, catalog_descendants, catalog_revoked,
    catalog_unknown, catalog_reject, catalog_unavailable, catalog_owner_admission, catalog_revoke_last,
    catalog_all_revoked,
};

inline constexpr bool desktop_scenario(scenario mode) {
    return mode == scenario::user_desktop || mode == scenario::user_desktop_admin;
}
struct packet {
    u32 tag = magic;
    u16 format = version;
    operation op{};
    u8 result = 0;
    u64 sequence = 0;
    generation_mark expected{};
    generation_mark value{};
};
static_assert(sizeof(packet) == 144 && sizeof(generation_mark) == 64);

inline bool header(const packet& value, operation operation, u64 sequence) {
    return value.tag == magic && value.format == version && value.op == operation &&
        value.sequence == sequence;
}

struct pair {
    u32 transmit = 0;
    u32 receive = 0;
};

inline bool find_pair(u64 controller, u64 peer, pair& result) {
    pair found{};
    for (u32 i = 0; i < 32; ++i) {
        channel_info info{};
        const i64 value = sdk::channel_get(i, info);
        if (value == thread_error_not_found) {
            break;
        }
        if (value != 0 || info.version != channel_version || info.size != sizeof(info)) {
            return false;
        }
        if (info.controller_pid != controller || info.peer_pid != peer) {
            continue;
        }
        if (info.rights == channel_receive && found.receive == 0) {
            found.receive = info.handle;
        } else if (info.rights == channel_send && found.transmit == 0) {
            found.transmit = info.handle;
        } else {
            return false;
        }
    }
    result = found;
    return found.transmit != 0 && found.receive != 0;
}

inline bool create_pair(u64 first, u64 second, pair& result) {
    channel_create offer{channel_version, sizeof(channel_create), first, second, sizeof(packet), 0};
    const i64 transmit = sdk::channel_open(offer);
    if (transmit <= 0) return false;
    offer.sender_pid = second;
    offer.receiver_pid = first;
    const i64 receive = sdk::channel_open(offer);
    if (receive <= 0) {
        (void)sdk::channel_close(static_cast<u32>(transmit));
        return false;
    }
    result = {static_cast<u32>(transmit), static_cast<u32>(receive)};
    return true;
}

inline u64 deadline(u64 duration = exchange_ns) {
    const i64 now = sdk::syscall(sys_clock_monotonic);
    return now < 0 ? 0 : static_cast<u64>(now) + duration;
}

// The explicit launch acceptance profile reserves the existing sys81 quota for
// daemon backing plus real dynamic READY/ACK. Its supervisor/proxy test-control
// channel instead uses the existing sys84 transport. Default E/P2 stays sys81.
inline i64 control_send_wait(u32 handle, const void* data, u64 length, u64 end) {
#if XOS_PUMPKIN_LAUNCH_PROBE
    for (;;) {
        const auto ready = sdk::ipc_wait_until(handle, ipc_wait_mode::send, end);
        if (ready) return ready;
        const auto sent = sdk::ipc_send(handle, data, length);
        if (sent != sdk::ipc_error_full) return sent;
    }
#else
    return sdk::channel_send_wait(handle, data, length, end);
#endif
}
inline i64 control_receive_wait(u32 handle, void* data, u64 length, u64 end) {
#if XOS_PUMPKIN_LAUNCH_PROBE
    for (;;) {
        const auto ready = sdk::ipc_wait_until(handle, ipc_wait_mode::receive, end);
        if (ready) return ready;
        const auto received = sdk::ipc_recv(handle, data, length);
        if (received != sdk::ipc_error_empty) return received;
    }
#else
    return sdk::channel_receive_wait(handle, data, length, end);
#endif
}
#if XOS_PUMPKIN_LAUNCH_PROBE
inline constexpr char launch_control_service[] = "pumpkin-launch-proxy";
struct control_greeting { u32 magic = 0x31435050; u32 phase = 1; }; // PPC1, fixture only.
inline void close_control(pair& value) {
    if (value.transmit) (void)sdk::ipc_channel_close(value.transmit);
    if (value.receive) (void)sdk::ipc_channel_close(value.receive);
    value = {};
}
inline bool control_peer(const ipc_channel& channel, u64 expected) {
    u64 sender = 0, receiver = 0;
    return expected && channel.send && channel.receive && channel.send != channel.receive &&
        sdk::ipc_endpoint_peer(channel.send, sender) == 0 &&
        sdk::ipc_endpoint_peer(channel.receive, receiver) == 0 && sender == expected && receiver == expected;
}
inline bool accept_control(u64 child, pair& result) {
    const auto end = deadline();
    if (!end) return false;
    for (;;) {
        ipc_channel channel{};
        const auto accepted = sdk::ipc_name_try_accept(channel);
        if (!accepted) {
            pair candidate{channel.send, channel.receive};
            if (control_peer(channel, child)) {
                control_greeting hello{}, ack{}; ack.phase = 2;
                if (control_receive_wait(channel.receive, &hello, sizeof(hello), end) == sizeof(hello) &&
                    hello.magic == control_greeting{}.magic && hello.phase == 1 &&
                    control_send_wait(channel.send, &ack, sizeof(ack), end) == 0) {
                    result = candidate; return true;
                }
                close_control(candidate); return false;
            }
            close_control(candidate);
        } else if (accepted != process_error_would_block) return false;
        const auto now = sdk::syscall(sys_clock_monotonic);
        if (now < 0 || static_cast<u64>(now) >= end ||
            sdk::syscall(sys_sleep_until, static_cast<u64>(now) + 1'000'000)) return false;
    }
}
inline bool connect_control(u64 controller, pair& result) {
    ipc_channel channel{};
    if (sdk::ipc_name_connect(launch_control_service, channel)) return false;
    pair candidate{channel.send, channel.receive};
    const auto end = deadline();
    control_greeting hello{}, ack{};
    if (!end || !control_peer(channel, controller) ||
        control_send_wait(channel.send, &hello, sizeof(hello), end) ||
        control_receive_wait(channel.receive, &ack, sizeof(ack), end) != sizeof(ack) ||
        ack.magic != control_greeting{}.magic || ack.phase != 2) {
        close_control(candidate); return false;
    }
    result = candidate; return true;
}
#endif

struct bind_proxy {
    u64 daemon = 0;
};
struct supervisor_result {
    u8 pass = 0;
};

class client {
public:
    bool bind_bootstrap();
    bool live() const;
    generation_record_io io();

private:
    bool call(packet& message, packet& reply);
    u64 controller_ = 0;
    u64 proxy_ = 0;
    pair channel_{};
    u64 sequence_ = 0;
};

}
