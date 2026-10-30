// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
using namespace xos;

extern "C" int xos_user_main(const startup_info* startup) {
    const auto args = reinterpret_cast<const char* const*>(startup->argv);
    if (startup->argc > 1 && sdk::equal(args[1], "port")) {
        sdk::print("W1_PIO_FAULT_READY\n");
        u8 value;
        __asm__ volatile("inb %1, %0" : "=a"(value) : "Nd"(static_cast<u16>(0x3f8)));
        (void)value;
        sdk::print("W1_PIO_UNEXPECTED_ACCESS\n");
        return 1;
    }
    if (sdk::pio_grant(pio_grant_action::query, 0, pio_resource_com1) != process_error_denied) return 2;
    if (sdk::pio_grant(pio_grant_action::grant, sdk::pid(), pio_resource_com1) != process_error_denied) return 3;
    if (sdk::pio_grant(pio_grant_action::controller, 0, pio_resource_com1) != process_error_denied) return 4;
    if (sdk::pio_grant(pio_grant_action::recover, 0, pio_resource_com1) != process_error_denied) return 5;
    sdk::print("W1_PIO_DENIED_OK\n");
    return 0;
}
