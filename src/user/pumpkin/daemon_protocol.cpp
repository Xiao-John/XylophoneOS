// SPDX-License-Identifier: Apache-2.0
#include "daemon_protocol.hpp"

namespace xos::user::pumpkin {
namespace {

bool zero_id(const wire_id& value) {
    return value.number == 0 && !has_bytes(value.scope.bytes, sizeof(value.scope.bytes));
}

bool valid_id(const wire_id& value) {
    return value.number != 0 && has_bytes(value.scope.bytes, sizeof(value.scope.bytes));
}

bool uses_name(wire_operation operation) {
    return operation == wire_operation::authenticate || operation == wire_operation::create_account ||
        operation == wire_operation::lookup_account;
}

bool valid_request(const wire_request& request, const wire_extension* extension) {
    const auto operation = request.operation;
    if (request.version != wire_version || request.reserved != 0 ||
        operation < wire_operation::authenticate ||
        (operation > wire_operation::revoke_account &&
            (!extension || !extension->invoke || operation < extension->first || operation > extension->last)) ||
        request.name_length > name_limit) {
        return false;
    }
    if (operation == wire_operation::grant_login_resource) {
        if (request.name_length != sizeof(login_resource_grant) || !valid_id(request.token)) { return false; }
    } else if (operation == wire_operation::admit_resource_broker) {
        if (request.name_length != sizeof(resource_broker_grant) || !zero_id(request.token)) { return false; }
    } else if (operation == wire_operation::begin_resource_read) {
        if (request.name_length != sizeof(u64) || !valid_id(request.token)) { return false; }
    } else if (operation >= wire_operation::put_named_resource && operation <= wire_operation::erase_named_resource) {
        if (request.name_length != sizeof(named_resource_request) ||
            (operation == wire_operation::erase_named_resource ? !zero_id(request.token) : !valid_id(request.token))) {
            return false;
        }
    } else if (uses_name(operation) ? request.name_length == 0 || !zero_id(request.token)
                                    : request.name_length != 0 || !valid_id(request.token)) {
        return false;
    }
    for (usize index = request.name_length; index < name_limit; ++index) {
        if (request.name[index] != 0) {
            return false;
        }
    }
    return operation == wire_operation::authenticate || !has_bytes(request.key.bytes, secret_bytes);
}

wire_status to_wire_status(status result) {
    switch (result) {
    case status::ok: return wire_status::ok;
    case status::invalid: return wire_status::invalid;
    case status::denied: return wire_status::denied;
    case status::not_found: return wire_status::not_found;
    case status::conflict: return wire_status::conflict;
    case status::exhausted: return wire_status::exhausted;
    case status::unavailable: return wire_status::unavailable;
    case status::corrupt: return wire_status::corrupt;
    case status::io_error: return wire_status::io_error;
    case status::outcome_unknown: return wire_status::outcome_unknown;
    }
    return wire_status::unavailable;
}

status invoke(service_core& core, const connection_id& connection, const wire_request& request,
              u64 now, wire_reply& reply) {
    const auto name = account_name{request.name, request.name_length};
    const auto session = session_id{request.token.scope, request.token.number};
    const auto identity = identity_id{request.token.scope, request.token.number};
    identity_id returned_identity;
    switch (request.operation) {
    case wire_operation::authenticate: {
        session_id output;
        const auto result = core.authenticate(connection, now, name, request.key, output);
        reply.token = {output.incarnation, output.number};
        return result;
    }
    case wire_operation::logout:
        return core.logout(connection, now, session);
    case wire_operation::identity: {
        const auto result = core.session_identity(connection, now, session, returned_identity);
        reply.token = {returned_identity.realm, returned_identity.number};
        return result;
    }
    case wire_operation::create_account: {
        const auto result = core.create_account(connection, now, name, returned_identity, reply.key);
        reply.token = {returned_identity.realm, returned_identity.number};
        return result;
    }
    case wire_operation::lookup_account: {
        account_description account;
        const auto result = core.lookup_account(connection, now, name, account);
        reply.token = {account.identity.realm, account.identity.number};
        reply.flags = account.disabled ? 1u : 0u;
        return result;
    }
    case wire_operation::rotate_credential:
        return core.rotate_credential(connection, now, identity, reply.key);
    case wire_operation::revoke_account:
        return core.revoke_account(connection, now, identity);
    case wire_operation::grant_login_resource:
    case wire_operation::read_login_resource:
    case wire_operation::admit_resource_broker:
    case wire_operation::begin_resource_read:
    case wire_operation::put_named_resource:
    case wire_operation::read_named_resource:
    case wire_operation::erase_named_resource:
        break;
    }
    return status::invalid;
}

}

bool dispatch_request(service_core& core, const connection_id& connection, u64& last_sequence,
                      const wire_request& request, u64 now, wire_reply& reply,
                      const wire_extension* extension) {
    wipe_bytes(&reply, sizeof(reply));
    reply = {};
    if (!valid_request(request, extension) ||
        request.sequence == 0 || request.sequence != last_sequence + 1) {
        return false;
    }
    last_sequence = request.sequence;
    reply.operation = request.operation;
    reply.sequence = request.sequence;
    if (request.deadline <= now || request.deadline - now > max_request_ns) {
        reply.result = wire_status::expired;
        return true;
    }
    const auto result = request.operation > wire_operation::revoke_account
        ? extension->invoke(extension->context, core, connection, request, now, reply)
        : invoke(core, connection, request, now, reply);
    reply.result = to_wire_status(result);
    return true;
}

bool valid_reply(const wire_request& request, const wire_reply& reply) {
    if (reply.version != wire_version || reply.operation != request.operation ||
        reply.sequence != request.sequence || reply.result > wire_status::expired) {
        return false;
    }
    const bool has_key = has_bytes(reply.key.bytes, secret_bytes);
    if (reply.result != wire_status::ok) {
        return reply.flags == 0 && zero_id(reply.token) && !has_key;
    }
    const bool expects_token = uses_name(request.operation) || request.operation == wire_operation::identity ||
        request.operation == wire_operation::begin_resource_read || request.operation == wire_operation::put_named_resource ||
        request.operation == wire_operation::read_named_resource;
    const bool expects_key = request.operation == wire_operation::create_account ||
        request.operation == wire_operation::rotate_credential;
    return (expects_token ? valid_id(reply.token) : zero_id(reply.token)) && expects_key == has_key &&
        (request.operation == wire_operation::lookup_account ? reply.flags <= 1 :
            request.operation == wire_operation::read_login_resource ||
            request.operation == wire_operation::read_named_resource || reply.flags == 0);
}

}
