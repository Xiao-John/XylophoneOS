// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/observation.hpp>
#include <xos/dynamic.hpp>
#include <xos/net_service_client.hpp>

namespace xos::observation {
// Identity of an already loaded, validated snapshot selected by this owner.
// An optional provider bridge supplies this without adding TLS to the base SDK.
struct trust_snapshot { u64 generation; u8 sha256[32]; };
using trust_capture_fn = status (*)(const void*, trust_snapshot&);
struct sources {
    u64 process_target = 0; // 0=self; otherwise a direct child of this controller.
    u32 service_endpoint = 0; // Held generic endpoint, never a client-supplied PID.
    const dynamic::activation_catalog* runtime = nullptr;
    net2::session_client* network = nullptr;
    const void* trust_context = nullptr;
    trust_capture_fn trust_capture = nullptr;
    static status capture(void* context, kind subject, u64 deadline_ns, response& output);
};
}
