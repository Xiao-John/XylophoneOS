// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <xos/elf.hpp>
#include <xos/spawn.hpp>

namespace xos::execution {

enum class candidate_kind {
    missing,
    directory,
    executable,
    not_executable,
    incompatible,
    unreadable
};

struct candidate {
    char path[256];
    candidate_kind kind;
    elf::error format_error;
    i64 error;
};

candidate inspect(const char* path);
candidate resolve(const char* name, const char* search_path);
const char* kind_name(candidate_kind kind);

enum class launch_stage { none, open, inspect, prepare, create, map, start };

struct launch_diagnostic {
    launch_stage stage;
    i64 code;
    elf::error format_error;
};

i64 spawn_file_diagnosed(const char* path, u32 argc, const char* const* argv,
                         const sdk::spawn_options& options,
                         launch_diagnostic& diagnostic);

}
