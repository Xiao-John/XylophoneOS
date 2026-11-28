// SPDX-License-Identifier: Apache-2.0
#pragma once

#include "trust_store.hpp"
#include <xos/observation_sources.hpp>

namespace native_tls {

// Optional bridge: the base observation SDK does not include or link Mbed TLS.
// The owner selects an already loaded store for its new connections and lends
// that object as sources::trust_context. It must keep the object alive through
// capture and serialize selection changes/destruction with reads, as required
// by the existing single-threaded native TLS profile. Existing TLS streams own
// their CA copies; this observation does not describe their selected anchors.
inline xos::observation::status capture_trust_observation(
    const void* context, xos::observation::trust_snapshot& output) {
    output = {};
    if (!context) return xos::observation::status::unavailable;
    trust_store_pin pin{};
    if (!static_cast<const trust_store*>(context)->capture_pin(pin))
        return xos::observation::status::unavailable;
    output.generation = pin.generation;
    for (size_t i = 0; i < sizeof pin.sha256; ++i) output.sha256[i] = pin.sha256[i];
    return xos::observation::status::ok;
}

}
