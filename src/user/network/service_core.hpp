// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/net_service_abi.hpp>

namespace xos::user::network {
// The production service uses lwIP. Tests may inject a transport at this narrow
// boundary; authentication, limits and lifecycle remain this exact implementation.
struct stack_api {
    void* context;
    i64 (*open)(void*, u32, net2::protocol, u32, u16, u64);
    i64 (*status)(void*, u32, u32&);
    i64 (*send)(void*, u32, const u8*, u32);
    i64 (*receive)(void*, u32, u8*, u32, u32&, u32&);
    i64 (*close)(void*, u32, bool);
    u32 (*dropped)(void*);
};
class service_core {
public:
    void initialize(u64 controller, const stack_api& stack);
    i64 attach(u64 peer, u64 now);
    void detach(u32 session);
    void expire(u64 now);
    bool alive(u32 session) const;
    u64 peer(u32 session) const;
    u64 generation(u32 session) const;
    bool dispatch(u32 session, const net2::message& request, u32 bytes,
                  u64 now, net2::message& reply);
    void shutdown();
    bool stopping() const { return stopping_; }
    u32 session_count() const;
    u32 connection_count() const;
private:
    struct session { u64 peer, last_sequence, last_active, generation; } sessions_[net2::session_limit]{};
    struct connection { u64 handle; u32 owner; } connections_[net2::connection_limit]{};
    u64 revoked_[16]{}, controller_ = 0, next_handle_ = 1, next_generation_ = 1;
    stack_api stack_{};
    bool stopping_ = false;
    i64 find_connection(u32 owner, u64 handle) const;
    void release(u32 slot);
};
}
