// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "files_private_lease.hpp"
#include "../pumpkin/session_limits.hpp"
#include <xos/thread_abi.hpp>

namespace xos::user::files_private_storage {

inline constexpr u64 lease_ns = 30'000'000'000ull;
inline constexpr u64 desktop_lease_ns = pumpkin::connection_lifetime_ns + pumpkin::desktop_backing_grace_ns;
inline constexpr u64 reply_ns = 500'000'000ull;
inline constexpr u64 exchange_ns = 5'000'000'000ull;

enum class lease_profile { short_operation, desktop };

// Bounded transport helpers used only by the profile's compiled-in endpoints.
inline bool peer_matches(const ipc_channel& channel, u64 expected) {
    u64 send_peer = 0, receive_peer = 0;
    return expected != 0 && channel.send != 0 && channel.receive != 0 && channel.send != channel.receive &&
        sdk::ipc_endpoint_peer(channel.send, send_peer) == 0 &&
        sdk::ipc_endpoint_peer(channel.receive, receive_peer) == 0 &&
        send_peer == expected && receive_peer == expected;
}

inline void close_pair(ipc_channel& channel) {
    if (channel.send != 0) {
        (void)sdk::ipc_channel_close(channel.send);
    }
    if (channel.receive != 0) {
        (void)sdk::ipc_channel_close(channel.receive);
    }
    channel = {};
}

inline bool wait_tick(i64 deadline) {
    const i64 now = sdk::syscall(sys_clock_monotonic);
    return now >= 0 && now < deadline &&
        sdk::syscall(sys_sleep_until, static_cast<u64>(now) + 1'000'000) == 0;
}

inline i64 exchange_deadline() {
    const i64 now = sdk::syscall(sys_clock_monotonic);
    if (now < 0 || static_cast<u64>(now) > (~u64{0} >> 1) - exchange_ns) {
        return -1;
    }
    return now + static_cast<i64>(exchange_ns);
}

slot_io private_slot_io();

class broker {
public:
    explicit broker(slot_io io, lease_profile profile = lease_profile::short_operation)
        : lease_(io), lease_duration_(profile == lease_profile::desktop ? desktop_lease_ns : lease_ns) {}
    bool establish_bootstrap();
    bool bootstrap_session(const file_session_info& client) const;
    grant_reply grant(const grant_request& request, const file_session_info& source, u32 source_index, bool healthy);
    void revoke();
    void poll(bool healthy);

private:
    bool ready_for_request(u64 now);
    bool controller_alive() const;

    slot_lease lease_;
    const u64 lease_duration_;
    ipc_channel bootstrap_{};
    ipc_channel client_{};
    u32 controller_index_ = 0;
    u64 controller_ = 0;
    u64 deadline_ = 0;
    u64 reply_deadline_ = 0;
    request request_{};
    response response_{};
};

}
