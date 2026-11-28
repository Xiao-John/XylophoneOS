// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/net_service_abi.hpp>
#include "egress_policy.hpp"

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
    i64 (*readiness)(void*, u32, net2::readiness_snapshot&) = nullptr;
    i64 (*shutdown_write)(void*, u32) = nullptr;
    i64 (*lease_status)(void*, net2::lease_snapshot&) = nullptr;
};
using resolver_completion = void (*)(void*, u64, i64, u32, u64, u64);
struct resolver_api {
    void* context;
    void (*configure)(void*, u32);
    i64 (*start)(void*, const char*, u64, resolver_completion, void*);
    void (*cancel)(void*, u64);
    void (*configure_pair)(void*, u32, u32) = nullptr;
};
class service_core {
public:
    void initialize(u64 controller, const stack_api& stack, const resolver_api& resolver = {},
                    u32 configured_resolver = 0, const egress_policy& policy = default_egress_policy,
                    u32 secondary_resolver = 0);
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
    void enable_dhcp();
    bool publish_dhcp(u32 address, u32 mask, u32 gateway, u32 resolver, u32 secondary_resolver = 0);
private:
    struct session { u64 peer, last_sequence, last_active, generation; } sessions_[net2::session_limit]{};
    struct connection { u64 handle; u32 owner; } connections_[net2::connection_limit]{};
    struct ticket {
        u64 id, generation, epoch, deadline, expiry;
        i64 result;
        u32 address;
    } tickets_[net2::client_sessions]{};
    u64 revoked_[net2::revoked_peer_limit]{}, controller_ = 0, next_handle_ = 1, next_generation_ = 1;
    stack_api stack_{};
    resolver_api resolver_{};
    egress_policy policy_{};
    u32 resolver_address_ = net2::permitted_address;
    u32 secondary_resolver_ = 0;
    u32 address_ = net2::static_address, mask_ = net2::static_mask, gateway_ = net2::permitted_address;
    net2::network_mode mode_ = net2::network_mode::disabled;
    u64 config_epoch_ = 1, next_ticket_ = 1;
    bool stopping_ = false;
    i64 find_connection(u32 owner, u64 handle) const;
    void release(u32 slot);
    bool resolve(u32 slot, const net2::message& request, u64 now, net2::message& reply);
    void retire_ticket(u32 slot);
    void configure_resolvers(bool enabled);
    static void complete_ticket(void* context, u64 id, i64 result, u32 address, u64 expiry, u64 received);
};
}
