// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
using namespace xos;

extern "C" int xos_user_main(const startup_info*) {
    if (sdk::irq_event(irq_event_action::bind, pio_resource_com1) != process_error_denied) return 1;
    if (sdk::irq_event(irq_event_action::wait, 1, 0) != process_error_denied) return 2;
    if (sdk::irq_event(irq_event_action::ack, 1, 1) != process_error_denied) return 3;
    sdk::print("W1_IRQ_DENIED_OK\n");
    return 0;
}
