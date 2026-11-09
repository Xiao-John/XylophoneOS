// SPDX-License-Identifier: Apache-2.0
// Narrow PC Speaker safety stop; tone sequencing and PIT programming stay in user space.
#include "arch/x86_64/io.hpp"
#include <xos/platform.hpp>

namespace xos::platform {
void pc_speaker_stop() {
    // Clear PIT2 gate and speaker data enable, preserving every other port bit.
    const u8 value = arch::in_byte(0x61);
    arch::out_byte(0x61, static_cast<u8>(value & ~0x03u));
}
}
