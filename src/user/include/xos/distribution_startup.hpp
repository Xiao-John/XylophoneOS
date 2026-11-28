// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/process_abi.hpp>

namespace xypm_distribution {
inline constexpr xos::u64 publisher_startup_magic = 0x315055534d505958ULL;
enum class publisher_phase : xos::u32 { offer = 1, broker = 2, connected = 3, delegated = 4 };
// A rendezvous name discovers the actual parent; it grants no publisher role.
// Each endpoint is authenticated against the kernel-observed peer.
struct publisher_startup {
    xos::u64 magic = publisher_startup_magic;
    publisher_phase phase{};
    xos::u32 reserved = 0;
    xos::u64 broker_pid = 0;
    xos::ipc_channel channel{};
    char broker_name[64]{};
};
static_assert(sizeof(publisher_startup) == 96);
}
