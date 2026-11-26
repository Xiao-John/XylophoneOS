// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "daemon_protocol.hpp"
#include "named_resource_store.hpp"

namespace xos::user::pumpkin {
status select_named_resource(named_resource_store& store, service_core& core, const connection_id& connection,
                             const session_id& session, const named_resource_request& input, u64 now,
                             named_resource_record& selected);
status invoke_named_resource(named_resource_store& store, service_core& core, const connection_id& connection,
                             bool registrar, const wire_request& request, u64 now, wire_reply& reply);
}
