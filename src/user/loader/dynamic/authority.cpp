// SPDX-License-Identifier: Apache-2.0
#include "authority.hpp"
#include <xos/sdk.hpp>
#include <xos/thread_abi.hpp>

namespace xos::dynamic {
namespace {
catalog::authority authority_binding{};
launch::artifact authority_owner{};
bool authority_set = false;

bool bytes_equal(const void* a, const void* b, usize size) {
    return __builtin_memcmp(a, b, size) == 0;
}
bool nonzero(const u8* data, usize length) {
    for (usize i = 0; i < length; ++i) { if (data[i]) { return true; } }
    return false;
}
void close_channel(ipc_channel& channel) {
    if (channel.send) { (void)sdk::ipc_channel_close(channel.send); }
    if (channel.receive) { (void)sdk::ipc_channel_close(channel.receive); }
    channel = {};
}
i64 now_before(u64 deadline, u64& now) {
    const auto value = sdk::syscall(sys_clock_monotonic);
    if (value < 0) { return value; }
    now = static_cast<u64>(value);
    if (!deadline || deadline == ~u64{0} || deadline <= now) { return thread_error_timeout; }
    return deadline - now <= startup_deadline_limit_ns ? 0 : process_error_invalid;
}
i64 query(const catalog::authority& authority, u64 deadline, catalog::query_reply& reply) {
    reply = {};
    if (!catalog::authority_valid(authority) || catalog::authority_empty(authority)) { return process_error_denied; }
    u64 now = 0;
    auto result = now_before(deadline, now);
    if (result) { return result; }
    ipc_channel channel{};
    result = sdk::ipc_name_connect(authority.service, channel);
    if (result) { return result; }
    u64 sender = 0, receiver = 0;
    if (!channel.send || !channel.receive || channel.send == channel.receive ||
        sdk::ipc_endpoint_peer(channel.send, sender) || sdk::ipc_endpoint_peer(channel.receive, receiver) ||
        sender != authority.daemon || receiver != authority.daemon) {
        close_channel(channel); return process_error_denied;
    }
    catalog::query_request request{};
    request.sequence = 1;
    request.deadline = deadline - now > 5'000'000'000ull ? now + 5'000'000'000ull : deadline;
    const auto exchange_deadline = request.deadline;
    __builtin_memcpy(request.realm, authority.realm, sizeof(request.realm));
    result = sdk::ipc_send(channel.send, &request, sizeof(request));
    while (!result) {
        const auto received = sdk::ipc_recv(channel.receive, &reply, sizeof(reply));
        if (received != process_error_would_block) {
            result = received == sizeof(reply) ? 0 : received < 0 ? received : process_error_invalid;
            break;
        }
        result = now_before(exchange_deadline, now);
        if (!result) { result = sdk::syscall(sys_sleep_until,
            now + (exchange_deadline - now < 1'000'000 ? exchange_deadline - now : 1'000'000)); }
    }
    close_channel(channel);
    if (result) { reply = {}; return result; }
    const auto& value = reply.catalog;
    if (reply.magic != catalog::query_magic || reply.version != catalog::query_version || reply.sequence != 1 ||
        reply.status != catalog::query_status::ok || reply.reserved || !reply.revision || !reply.authorization_epoch ||
        !bytes_equal(reply.realm, authority.realm, 16) || !value.count || value.count > catalog::root_limit ||
        value.active >= value.count || !value.epoch || value.reserved || (value.revoked >> value.count) ||
        (value.revoked & (1u << value.active)) || !nonzero(value.sdk_sha256, 32)) { return process_error_denied; }
    return now_before(deadline, now);
}
bool admitted(const catalog::snapshot& value, const launch::artifact& artifact, bool empty_allowed) {
    if (!artifact.id) { return empty_allowed && !nonzero(artifact.sha256, sizeof(artifact.sha256)); }
    for (u32 i = 0; i < value.count; ++i) {
        if (!(value.revoked & (1u << i)) && value.roots[i].generation == artifact.id &&
            bytes_equal(value.roots[i].manifest_sha256, artifact.sha256, 32)) { return true; }
    }
    return false;
}
}

error read_authority(const catalog::authority& authority, u64 deadline, launch_policy& policy) {
    policy = {};
    catalog::query_reply reply{};
    if (query(authority, deadline, reply)) { return error::io; }
    policy.count = reply.catalog.count; policy.active = reply.catalog.active;
    policy.sequence = reply.catalog.epoch; policy.revoked = reply.catalog.revoked;
    __builtin_memcpy(policy.sdk_sha256, reply.catalog.sdk_sha256, 32);
    for (u32 i = 0; i < policy.count; ++i) {
        policy.roots[i].root.id = reply.catalog.roots[i].generation;
        __builtin_memcpy(policy.roots[i].root.sha256, reply.catalog.roots[i].manifest_sha256, 32);
        __builtin_memcpy(policy.roots[i].manifest, reply.catalog.roots[i].manifest, sizeof(policy.roots[i].manifest));
    }
    return error::none;
}
error restore_authority(const catalog::authority& authority, const launch::artifact& owner) {
    if (!catalog::authority_valid(authority)) { return error::identity; }
    if (static_cast<bool>(owner.id) != nonzero(owner.sha256, sizeof(owner.sha256))) { return error::identity; }
    if (authority_set) {
        return authority == authority_binding && bytes_equal(&owner, &authority_owner, sizeof(owner)) ?
            error::none : error::state;
    }
    authority_binding = authority; authority_owner = owner; authority_set = true;
    return error::none;
}
error export_authority(catalog::authority& output) {
    output = authority_binding;
    return error::none;
}
i64 authority_admission(const launch::artifact& current, const launch::artifact& requested, u64 deadline) {
    if (catalog::authority_empty(authority_binding)) { return 0; }
    catalog::query_reply reply{};
    const auto result = query(authority_binding, deadline, reply);
    if (result) { return result; }
    // A new child's launch-control current artifact is empty. The calling
    // process's capsule identity must independently remain authorized, including
    // when it chooses another still-approved target after its own revocation.
    return admitted(reply.catalog, authority_owner, true) && admitted(reply.catalog, current, true) &&
        admitted(reply.catalog, requested, false) ? 0 : process_error_denied;
}
}
