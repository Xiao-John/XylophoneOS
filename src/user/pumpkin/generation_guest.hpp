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
    user_named_read, user_named_put, user_named_erase, user_named_import,
};
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
