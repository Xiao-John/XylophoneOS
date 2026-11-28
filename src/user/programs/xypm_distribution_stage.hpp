// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "xypm_distribution.hpp"
#include <xos/file_client.hpp>

namespace xypm_distribution {
struct staging_context {
    xos::file::client files{};
    xos::u32 handle = 0, pin_count = 0, checkpoints = 0;
    xos::u32 pins[xos::dynamic::generation_max_objects + 1]{};
    xos::i64 native_error = 0;
    bool quarantined = false;
};
void stage(staging_context& state, const char* repository, const plan& prepared,
           uint64_t absolute_deadline, bool (*canonical_path)(const char*));
void release_staging(staging_context& state);
}
