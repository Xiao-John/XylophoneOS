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

enum class launch_stage { none, open, inspect, prepare, create, map, start, file_setup };

struct launch_diagnostic {
    launch_stage stage;
    i64 code;
    elf::error format_error;
};

struct image_receipt { u8 digest[32]; u32 size; };

// Independent, versioned output; spawn_options and existing runtime hooks keep
// their layouts. A negative spawn result alone never proves child destruction.
struct launch_abort_outcome {
    u32 version = 1, size = sizeof(launch_abort_outcome);
    u64 pid = 0;
    u32 never_started = 0, abort_attempted = 0;
    i64 abort_result = 0;
};
static_assert(sizeof(launch_abort_outcome) == 32);

i64 spawn_file_diagnosed(const char* path, u32 argc, const char* const* argv,
                         const sdk::spawn_options& options,
                         launch_diagnostic& diagnostic);

i64 spawn_file_diagnosed_receipt(const char* path, u32 argc, const char* const* argv,
                                 const sdk::spawn_options& options,
                                 launch_diagnostic& diagnostic, image_receipt& receipt);
i64 spawn_verified_file(const char* path, u32 argc, const char* const* argv,
                        const sdk::spawn_options& options, const image_receipt& expected);
i64 spawn_verified_static_file(const char* path, u32 argc, const char* const* argv,
                               const sdk::spawn_options& options, const image_receipt& expected,
                               launch_abort_outcome& outcome);

// Static bootstrap adapter for a verified public dynamic closure. The caller
// retains the same pin. prepare runs after all ELF copies and before either
// spawn or same-PID exec commit; a failure aborts the building image.
i64 spawn_pinned_image(const char* name, u64 size, elf::read_exact_fn read,
                       void* context, u32 argc, const char* const* argv,
                       const sdk::spawn_options& options, launch_diagnostic& diagnostic,
                       u64 absolute_deadline, i64 (*prepare)(u64, void*), void* prepare_context);

}
