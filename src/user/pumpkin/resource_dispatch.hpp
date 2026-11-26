// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "service_core.hpp"

namespace xos::user::pumpkin {

struct resource_request {
    session_id session;
    u64 handle;
    u32 operation;
};

struct resolved_resource {
    checked_rights authority;
    owner_record ownership;
    u64 open_description;
};

// The resource service supplies both records from its own current state.
// It pins the resolved object and open description across this dispatch or
// serializes changes with dispatch. Labels come from the resource service.
struct resource_dispatch_io {
    void* context = nullptr;
    bool (*resolve)(void*, const connection_id&, u64 handle, resolved_resource&) = nullptr;
    status (*execute)(void*, const resource_key&, u64 open_description, u32 operation) = nullptr;
};

// Single-loop adapter. The caller and time come from the trusted transport.
// The checked operation executes once against the resolved object, and no
// reusable authorization result is returned to the application.
status dispatch_resource(service_core& core, const connection_id& connection, u64 now,
                         const resource_request& request, const resource_dispatch_io& io);

}
