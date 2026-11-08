// SPDX-License-Identifier: Apache-2.0
#pragma once

#include "dispatcher.hpp"
#include "transport.hpp"

namespace xos::interactium {

inline constexpr u32 max_wire_message = sizeof(wire_header) + max_wire_payload;

enum class loop_result : i32 {
    progressed = 0,
    again = 1,
    session_closed = 2,
    transport_error = -1,
    protocol_error = -2,
};

// One step is deliberately bounded: an outer service can multiplex endpoint
// readiness without letting one client monopolize the compositor.
class service_loop {
    protocol_dispatcher dispatcher_;
    service* service_ = nullptr;
    session_transport* transport_ = nullptr;
    bool closed_ = false;

public:
    service_loop(service& service, session_transport& transport)
        : dispatcher_(service, transport.authenticated_owner()), service_(&service), transport_(&transport) {}
    explicit service_loop(service& service) : dispatcher_(service, 0), service_(&service) {}

    void bind(session_transport& transport) {
        dispatcher_.bind(*service_, transport.authenticated_owner());
        transport_ = &transport;
        closed_ = false;
    }
    loop_result step();
    bool connected() const { return dispatcher_.connected(); }
};

} // namespace xos::interactium
