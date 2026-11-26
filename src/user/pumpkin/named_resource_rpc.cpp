// SPDX-License-Identifier: Apache-2.0
#include "named_resource_rpc.hpp"

namespace xos::user::pumpkin {

status select_named_resource(named_resource_store& store, service_core& core, const connection_id& connection,
                             const session_id& session, const named_resource_request& input, u64 now,
                             named_resource_record& selected) {
    if (store.lookup({input.name, input.length}, selected) != status::ok ||
        (input.generation && input.generation != selected.key.generation)) { return status::denied; }
    return core.authorize_owner(connection, now, session, {connection, selected.key, resource_read},
                                {selected.key, selected.owner, resource_read}, resource_read);
}

status invoke_named_resource(named_resource_store& store, service_core& core, const connection_id& connection,
                             bool registrar, const wire_request& request, u64 now, wire_reply& reply) {
    const bool reading = request.operation == wire_operation::read_named_resource;
    const bool binary = request.operation == wire_operation::put_named_binary;
    if (registrar == reading) { return status::denied; }
    named_resource_request input{};
    __builtin_memcpy(&input, request.name, sizeof(input));
    const account_name name{input.name, input.length};
    if (!valid_named_request(input, binary || request.operation == wire_operation::put_named_resource)) {
        return status::invalid;
    }

    named_resource_record entry{};
    if (reading) {
        const auto result = select_named_resource(store, core, connection, {request.token.scope, request.token.number},
                                                  input, now, entry);
        if (result == status::ok) {
            if (entry.length != sizeof(reply.flags)) { return status::denied; }
            reply.token = {entry.key.registry, entry.key.generation};
            __builtin_memcpy(&reply.flags, entry.bytes, sizeof(reply.flags));
        }
        return result;
    }

    const auto found = store.lookup(name, entry);
    if ((found == status::ok && input.generation != entry.key.generation) ||
        (found == status::not_found && input.generation != 0)) { return status::conflict; }
    if (found != status::ok && found != status::not_found) { return found; }
    if (request.operation == wire_operation::erase_named_resource) {
        const auto result = store.erase(name, entry.key);
        if (!store.live()) { core.stop(); }
        return result;
    }
    static_assert(secret_bytes == named_resource_bytes);
    const auto* bytes = reinterpret_cast<const u8*>(&input.data);
    usize length = sizeof(input.data);
    if (binary) {
        length = input.data;
        bytes = request.key.bytes;
        if (!length || length > named_resource_bytes || has_bytes(bytes + length, named_resource_bytes - length)) {
            return status::invalid;
        }
    }
    const auto result = store.put(name, entry.key, {request.token.scope, request.token.number}, bytes, length);
    if (!store.live()) { core.stop(); }
    if (result != status::ok) { return result; }
    if (store.lookup(name, entry) != status::ok) { return status::outcome_unknown; }
    reply.token = {entry.key.registry, entry.key.generation};
    return status::ok;
}
}
