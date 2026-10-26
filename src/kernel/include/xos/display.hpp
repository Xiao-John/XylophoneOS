// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/boot_info.hpp>
#include <xos/display_abi.hpp>
namespace xos::display {
void init(const boot_info& info);
bool available();
display_mode mode();
bool valid(const display_present& request);
void write(u64 offset, const u8* bytes, u64 length);
void input_init();
void input_irq(u8 irq, u64 now);
void input_reset(bool focused);
bool input_read(display_event& event);
}
