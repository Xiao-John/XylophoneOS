// SPDX-License-Identifier: Apache-2.0
#include "service_loop.hpp"

namespace xos::interactium {

loop_result service_loop::step() {
    if (transport_ == nullptr) return loop_result::transport_error;
    if (closed_) return loop_result::session_closed;
    if (transport_->closed()) {
        dispatcher_.transport_closed();
        transport_->close();
        closed_ = true;
        return loop_result::session_closed;
    }
    if (closing_) {
        if (!transport_->reply_drained()) return loop_result::again;
        transport_->close();
        closed_ = true;
        return loop_result::session_closed;
    }

    u8 request[max_wire_message]{};
    u8 response[max_wire_message]{};
    u32 request_size = 0;
    const i32 received = transport_->receive(request, sizeof(request), request_size);
    if (received == transport_again) return loop_result::again;
    if (received < 0 || static_cast<u32>(received) != request_size ||
        request_size > sizeof(request) || request_size == 0) {
        dispatcher_.transport_closed();
        transport_->close();
        closed_ = true;
        return loop_result::transport_error;
    }

    u32 response_size = 0;
    const i32 dispatched = dispatcher_.dispatch(request, request_size, response,
                                                sizeof(response), response_size);
    if (response_size != 0 && transport_->send(response, response_size) !=
                                   static_cast<i32>(response_size)) {
        dispatcher_.transport_closed();
        transport_->close();
        closed_ = true;
        return loop_result::transport_error;
    }
    if (!dispatcher_.connected()) {
        closing_ = true;
        return loop_result::progressed;
    }
    return dispatched == 0 ? loop_result::progressed : loop_result::protocol_error;
}

} // namespace xos::interactium
