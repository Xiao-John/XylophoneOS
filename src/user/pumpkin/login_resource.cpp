// SPDX-License-Identifier: Apache-2.0
#include "login_resource.hpp"

namespace xos::user::pumpkin {
namespace {
constexpr u64 resource_number = 1;
}

status login_resource::invoke(service_core& core, const connection_id& connection, const ipc_channel& channel,
                              bool registrar, const wire_request& request, u64 now, wire_reply& reply) {
    if (request.operation == wire_operation::grant_login_resource) {
        if (!registrar || holder_ != 0) { return status::denied; }
        login_resource_grant grant{};
        __builtin_memcpy(&grant, request.name, sizeof(grant));
        const ipc_channel pair{grant.send, grant.receive};
        if (grant.holder == 0 || authenticated_peer(pair) != grant.holder) { return status::denied; }
        if (!files_.init()) { return status::io_error; }
        const identity_id owner{request.token.scope, request.token.number};
        const auto published = object_.publish({connection.incarnation, resource_number, 1}, connection.incarnation,
            owner, reinterpret_cast<const u8*>(&login_resource_value), sizeof(login_resource_value));
        if (published == status::ok) {
            holder_ = grant.holder;
            granted_ = pair;
        }
        return published;
    }

    if (registrar || holder_ == 0 || granted_.send != channel.send || granted_.receive != channel.receive ||
        authenticated_peer(channel) != holder_) { return status::denied; }
    const resource_request read{{request.token.scope, request.token.number}, resource_number, resource_read};
    sealed_blob_reply data{};
    const auto result = object_.read(core, {connection, true}, now, read, data);
    if (result != status::ok) { return result; }
    if (data.length != sizeof(reply.flags)) { return status::io_error; }
    __builtin_memcpy(&reply.flags, data.bytes, sizeof(reply.flags));
    return status::ok;
}
}
