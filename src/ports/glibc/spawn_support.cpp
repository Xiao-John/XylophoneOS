// SPDX-License-Identifier: Apache-2.0
#include "sysdeps/xos/xos_file_runtime.h"
#include <errno.h>
#include <limits.h>
#include <string.h>
#include <sys/types.h>
#include <xos/execution.hpp>
#include <xos/sdk.hpp>
#include <xos/thread_abi.hpp>

namespace {
using namespace xos;

i64 prepare_child(u64 child, void* context) {
    if (child > INT_MAX) { return process_error_resources; }
    if (!*static_cast<const bool*>(context)) { return 0; }
    return sdk::syscall(sys_process_authority, child,
                        static_cast<u64>(process_authority_mode::copy_from_caller));
}

int launch_error(i64 result, const execution::launch_diagnostic& diagnostic) {
    using stage = execution::launch_stage;
    if (diagnostic.stage == stage::open || diagnostic.stage == stage::file_setup) {
        if (result == static_cast<i64>(file::status::is_directory)) { return EACCES; }
        return static_cast<int>(-__xos_file_service_error(static_cast<int>(result)));
    }
    if (diagnostic.stage == stage::inspect) {
        if (result == thread_error_unsupported) { return ENOTSUP; }
        return diagnostic.format_error == elf::error::io ? EIO : ENOEXEC;
    }
    if (diagnostic.stage == stage::prepare) { return E2BIG; }
    if (result == process_error_denied || result == process_error_delegation) { return EPERM; }
    if (result == process_error_resources) {
        return diagnostic.stage == stage::create ? EAGAIN : ENOMEM;
    }
    if (result == process_error_busy || result == process_error_state) { return EBUSY; }
    if (result == process_error_invalid) { return EINVAL; }
    return EIO;
}

u32 vector_length(char* const* values, u32 maximum) {
    u32 count = 0;
    if (values != nullptr) {
        while (count <= maximum && values[count] != nullptr) { ++count; }
    }
    return count;
}
}

extern "C" int __xos_spawn_path(pid_t* output, const char* path, char* const argv[],
                                char* const envp[]) {
    using namespace xos;
    if (path == nullptr || argv == nullptr) { return EINVAL; }
    const auto length = strnlen(path, file::max_name);
    if (length == 0) { return ENOENT; }
    if (length == file::max_name) { return ENAMETOOLONG; }
    if (path[length - 1] == '/') { return ENOTDIR; }
    const u32 argc = vector_length(argv, process_max_args);
    const u32 env_count = vector_length(envp, startup_environment_max);
    if (argc == 0) { return EINVAL; }
    if (argc > process_max_args || env_count > startup_environment_max) { return E2BIG; }

    const i64 authority = sdk::syscall(sys_process_authority, sdk::pid(),
                                      static_cast<u64>(process_authority_mode::query));
    if (authority < 0) { return authority == process_error_denied ? EPERM : EIO; }
    bool inherit_create = authority == 1;
    xos_spawn_stdio snapshot{};
    const long locked = __xos_file_spawn_begin(&snapshot);
    if (locked < 0) { return static_cast<int>(-locked); }

    sdk::spawn_options options{};
    options.environment = envp;
    options.environment_count = env_count;
    options.prepare_child = prepare_child;
    options.prepare_context = &inherit_create;
    for (unsigned int fd = 0; fd < 3; ++fd) {
        options.stdio[fd] = snapshot.route[fd];
        options.file_handles[fd] = snapshot.file_handle[fd];
        options.open_flags[fd] = snapshot.open_flags[fd];
    }
    execution::launch_diagnostic diagnostic{};
    const i64 child = execution::spawn_file_diagnosed(path, argc, argv, options, diagnostic);
    __xos_file_spawn_end(&snapshot);
    if (child < 0) { return launch_error(child, diagnostic); }
    if (output != nullptr) { *output = static_cast<pid_t>(child); }
    return 0;
}

extern "C" int __xos_exec_path(const char* path, char* const argv[], char* const envp[]) {
    using namespace xos;
    if (!path || !argv) return EINVAL;
    const auto length = strnlen(path, file::max_name);
    if (!length) return ENOENT;
    if (length == file::max_name) return ENAMETOOLONG;
    if (path[length - 1] == '/') return ENOTDIR;
    const u32 argc = vector_length(argv, process_max_args);
    const u32 environment_count = vector_length(envp, startup_environment_max);
    if (!argc) return EINVAL;
    if (argc > process_max_args || environment_count > startup_environment_max) return E2BIG;
    const i64 now = sdk::syscall(sys_clock_monotonic);
    if (now < 0 || now > INT64_MAX - 30000000000LL) return EIO;
    const u64 deadline = static_cast<u64>(now) + 30000000000ULL;
    xos_exec_descriptors snapshot{};
    const auto captured = __xos_file_exec_begin(&snapshot, deadline);
    if (captured != 0) return static_cast<int>(-captured);
    sdk::spawn_options options{};
    options.replace_image = true;
    options.environment = envp;
    options.environment_count = environment_count;
    static_assert(sizeof(startup_descriptor) == sizeof(xos_file_startup_descriptor));
    options.descriptors = reinterpret_cast<const startup_descriptor*>(snapshot.items);
    options.descriptor_count = snapshot.count;
    if (snapshot.terminal_locked) {
        options.exec_channel_count = 2;
        options.exec_channels = snapshot.terminal_channels;
        options.exec_terminal_send_handle = snapshot.terminal_channels[0];
        options.exec_terminal_next_sequence = snapshot.terminal_sequence;
    }
    execution::launch_diagnostic diagnostic{};
    const i64 result = execution::spawn_file_diagnosed(path, argc, argv, options, diagnostic);
    __xos_file_exec_end(&snapshot, deadline);
    return result < 0 ? launch_error(result, diagnostic) : EIO;
}
