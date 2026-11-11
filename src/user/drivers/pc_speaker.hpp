// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/sdk.hpp>
#include <xos/audio_abi.hpp>

namespace xos::user::pc_speaker {
// Call only after the kernel granted resource pio_resource_pc_speaker.
i64 play(u32 frequency_hz);
}
