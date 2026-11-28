// SPDX-License-Identifier: Apache-2.0
#include <xos/dynamic_startup_abi.h>
#include <xos/launch_control.hpp>

namespace {
const xos_dynamic_startup_prefix* startup() {
    const auto* value = reinterpret_cast<const xos_dynamic_startup_prefix*>(XOS_DYNAMIC_STARTUP_ADDRESS);
    if (value->magic != XOS_DYNAMIC_STARTUP_MAGIC || value->version != XOS_DYNAMIC_STARTUP_VERSION
        || value->size < sizeof(*value) || value->size > 65536
        || value->reserved[0] || value->reserved[1] || value->reserved[2]) return nullptr;
    return value;
}
}
extern "C" __attribute__((visibility("hidden"))) void xos_rtld_public_failure() {
    const auto* value = startup();
    if (value) (void)xos::launch::notify_ready(value->control, value->artifact,
        xos::process_error_invalid, XOS_LAUNCH_PHASE_RELOCATE);
}
