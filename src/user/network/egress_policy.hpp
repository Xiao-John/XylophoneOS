// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/net_service_abi.hpp>

namespace xos::user::network {
inline constexpr u32 egress_rule_limit = 8;
struct egress_rule {
    u32 network, prefix;
    net2::protocol transport;
    u16 first_port, last_port;
};
struct egress_policy {
    egress_rule rules[egress_rule_limit];
    u32 count;
};
inline constexpr u32 prefix_mask(u32 prefix) {
    return prefix == 0 ? 0 : prefix <= 32 ? ~u32{0} << (32 - prefix) : 0;
}
inline constexpr bool valid_egress_policy(const egress_policy& policy) {
    if (policy.count > egress_rule_limit) return false;
    for (u32 i = 0; i < policy.count; ++i) {
        const auto& rule = policy.rules[i];
        if (rule.prefix > 32 || (rule.network & ~prefix_mask(rule.prefix)) ||
            (rule.transport != net2::protocol::tcp && rule.transport != net2::protocol::udp) ||
            !rule.first_port || rule.first_port > rule.last_port) return false;
    }
    return true;
}
inline constexpr egress_policy default_egress_policy{{
    {net2::permitted_address, 32, net2::protocol::tcp, 1, 65535},
    {net2::permitted_address, 32, net2::protocol::udp, 1, 65535}}, 2};
static_assert(valid_egress_policy(default_egress_policy));

// This policy is installation authority, never data received from DNS/DHCP.
// DHCP endpoints belong exclusively to the service's private control PCB.
inline constexpr bool egress_permitted(const egress_policy& policy, u32 address,
                                       net2::protocol transport, u16 port) {
    if (!valid_egress_policy(policy) || !port || !address || address == ~u32{0} ||
        (address >> 24) == 0 || (address >> 24) == 127 || (address >> 28) >= 14 ||
        (transport == net2::protocol::udp && (port == 67 || port == 68))) return false;
    for (u32 i = 0; i < policy.count; ++i) {
        const auto& rule = policy.rules[i];
        if (transport == rule.transport && port >= rule.first_port && port <= rule.last_port &&
            (address & prefix_mask(rule.prefix)) == rule.network) return true;
    }
    return false;
}
}
