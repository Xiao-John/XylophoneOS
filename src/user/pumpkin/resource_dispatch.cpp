// SPDX-License-Identifier: Apache-2.0
#include "resource_dispatch.hpp"

namespace xos::user::pumpkin {

status dispatch_resource(service_core& core, const connection_id& connection, u64 now,
                         const resource_request& request, const resource_dispatch_io& io) {
    if (request.handle == 0 || (request.operation != resource_read && request.operation != resource_write)) {
        return status::invalid;
    }
    if (io.resolve == nullptr || io.execute == nullptr) {
        return status::unavailable;
    }
    resolved_resource resolved{};
    if (!io.resolve(io.context, connection, request.handle, resolved) || resolved.open_description == 0) {
        return status::denied;
    }

    const auto authorization = core.authorize_owner(connection, now, request.session, resolved.authority,
                                                    resolved.ownership, request.operation);
    if (authorization != status::ok) {
        return authorization;
    }
    return io.execute(io.context, resolved.authority.object, resolved.open_description, request.operation);
}

}
