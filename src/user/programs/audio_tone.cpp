// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <xos/audio_abi.hpp>
#include <xos/thread_abi.hpp>
#include "../drivers/pc_speaker.hpp"

namespace {
xos::u32 parse_number(const char* text) {
    if (text == nullptr || *text == '\0') return 0;
    xos::u32 value = 0;
    while (*text != '\0') {
        if (*text < '0' || *text > '9') return 0;
        const xos::u32 digit = static_cast<xos::u32>(*text++ - '0');
        if (value > (0xffffffffu - digit) / 10) return 0;
        value = value * 10 + digit;
    }
    return value;
}
}

extern "C" int xos_user_main(const xos::startup_info* startup) {
    using namespace xos;
    const auto* argv = reinterpret_cast<const char* const*>(startup->argv);
    if (startup->argc != 3) return 2;
    const u32 frequency = parse_number(argv[1]);
    const u32 duration_ms = parse_number(argv[2]);
    if (duration_ms < audio::min_note_ms || duration_ms > audio::max_note_ms ||
        (frequency != 0 && (frequency < audio::min_frequency_hz || frequency > audio::max_frequency_hz)))
        return 2;
    if (frequency != 0 && user::pc_speaker::play(frequency) != 0) return 3;
    const i64 now = sdk::syscall(sys_clock_monotonic);
    if (now < 0 || static_cast<u64>(now) > thread_deadline_infinite -
                                            static_cast<u64>(duration_ms) * 1000000ull) {
        (void)sdk::pio_grant(pio_grant_action::release, 0, pio_resource_pc_speaker);
        return 4;
    }
    const i64 waited = sdk::syscall(sys_sleep_until,
        static_cast<u64>(now) + static_cast<u64>(duration_ms) * 1000000ull);
    const i64 released = sdk::pio_grant(pio_grant_action::release, 0, pio_resource_pc_speaker);
    if (waited != 0) return 5;
    return released == 0 ? 0 : 6; // A lease timeout already stopped the gate.
}
