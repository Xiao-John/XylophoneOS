// SPDX-License-Identifier: Apache-2.0
// Runs only under the dedicated supervisor's explicit COM1 grant.
#include <xos/sdk.hpp>
using namespace xos;

extern "C" int xos_user_main(const startup_info* startup) {
    if (startup->argc != 2) return 1;
    const auto args = reinterpret_cast<const char* const*>(startup->argv);
    if (sdk::pio_grant(pio_grant_action::controller, 0, pio_resource_com1) <= 0) return 2;
    if (sdk::equal(args[1], "inside")) {
        u8 line = 0, scratch = 0;
        __asm__ volatile("inb %1, %0" : "=a"(line) : "Nd"(static_cast<u16>(0x3fd)));
        __asm__ volatile("inb %1, %0" : "=a"(scratch) : "Nd"(static_cast<u16>(0x3ff)));
        (void)line; (void)scratch;
        return 0;
    }
    if (sdk::equal(args[1], "below")) {
        u8 value = 0;
        __asm__ volatile("inb %1, %0" : "=a"(value) : "Nd"(static_cast<u16>(0x3f7)));
    } else if (sdk::equal(args[1], "above")) {
        u8 value = 0;
        __asm__ volatile("inb %1, %0" : "=a"(value) : "Nd"(static_cast<u16>(0x400)));
    } else if (sdk::equal(args[1], "cross")) {
        u16 value = 0;
        __asm__ volatile("inw %1, %0" : "=a"(value) : "Nd"(static_cast<u16>(0x3ff)));
    } else return 3;
    return 4; // access outside the granted range must fault before this point
}
