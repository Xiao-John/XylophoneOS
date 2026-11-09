// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/types.hpp>

namespace xos::audio {
inline constexpr u32 protocol_version = 1;
inline constexpr u32 max_notes = 64;
inline constexpr u32 max_sessions = 8;
inline constexpr u32 min_frequency_hz = 40;
inline constexpr u32 max_frequency_hz = 5000;
inline constexpr u32 min_note_ms = 10;
inline constexpr u32 max_note_ms = 2000;
inline constexpr u32 max_sequence_ms = 10000;
inline constexpr char service_name[] = "xos-audio";

enum class operation : u32 { capabilities = 1, submit = 2, status = 3, cancel = 4, close = 5 };
enum class job_state : u32 {
    none = 0, accepted = 1, playing = 2, completed = 3,
    cancelled = 4, expired = 5, device_lost = 6
};

struct note { u32 frequency_hz; u32 duration_ms; };
struct request {
    u32 version, size, operation, note_count;
    u64 job_id;
    note notes[max_notes];
    u64 reserved;
};
struct response {
    u32 version, size, state, completed_notes;
    i64 result;
    u64 job_id;
    u32 max_notes, max_sequence_ms, min_frequency_hz, max_frequency_hz;
};
static_assert(sizeof(note) == 8 && sizeof(request) == 544 && sizeof(response) == 48);

inline i64 validate_sequence(const note* notes, u32 count) {
    if (notes == nullptr || count == 0 || count > max_notes) return -2;
    u32 total_ms = 0;
    for (u32 i = 0; i < count; ++i) {
        const note& item = notes[i];
        if (item.duration_ms < min_note_ms || item.duration_ms > max_note_ms) return -2;
        if (item.frequency_hz != 0 &&
            (item.frequency_hz < min_frequency_hz || item.frequency_hz > max_frequency_hz)) return -2;
        if (item.duration_ms > max_sequence_ms - total_ms) return -2;
        total_ms += item.duration_ms;
    }
    return 0;
}
}
